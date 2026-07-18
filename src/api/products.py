from fastapi import APIRouter,Depends,HTTPException,UploadFile,File
from sqlalchemy import select,func,delete as sql_delete
from sqlalchemy.orm import selectinload
from src.database import get_async_session
from src.auth.deps import get_current_user
from src.models.product import Product
from src.models.product_packaging_image import ProductPackagingImage
from src.models.media_asset import MediaAsset
from src.schemas.product import ProductCreate,ProductUpdate,ProductResponse,PaginatedProducts,ProductDraft,MainImageCandidateResponse,PackagingImageGenerateRequest,PackagingImageCandidateResponse
from src.services.category_service import get_owned_category
from src.services.product_validation import normalize_attributes,AttributeValidationError
from src.services.main_image_candidates import create_candidate,consume_candidate,build_packaging_image_prompt
from src.tools.image_gen import generate_image
from src.api.media import get_media_service
from src.services.media_service import MediaService
from src.media.storage import StorageError
from src.tasks.video_tasks import _fetch_provider_media
router=APIRouter(prefix='/products',tags=['products'])

async def owned_packaging_assets(db, user_id, asset_ids):
    if len(asset_ids) > 6 or len(set(asset_ids)) != len(asset_ids):
        raise HTTPException(422, 'Choose up to six distinct packaging images')
    assets = []
    for asset_id in asset_ids:
        asset = (await db.execute(select(MediaAsset).where(
            MediaAsset.id == asset_id, MediaAsset.owner_user_id == user_id,
            MediaAsset.status == 'available', MediaAsset.category == 'product_image',
        ))).scalar_one_or_none()
        if not asset:
            raise HTTPException(404, 'Packaging image asset not found')
        assets.append(asset)
    return assets

async def prepare(db,user,body):
 c=await get_owned_category(db,user.id,body.category_id,load_attributes=True)
 if not c: raise HTTPException(404,'Category not found')
 if c.template_version!=body.category_template_version: raise HTTPException(409,{'current_version':c.template_version})
 try: attrs=normalize_attributes(c.attributes,body.attributes)
 except AttributeValidationError as e: raise HTTPException(422,e.errors)
 return attrs

@router.post('/main-image/generate',response_model=MainImageCandidateResponse,status_code=201)
async def generate(body:ProductDraft,db=Depends(get_async_session),user=Depends(get_current_user)):
 await prepare(db,user,body)
 media=get_media_service(db)
 try:
  c=await create_candidate(db,user.id,body,media,_fetch_provider_media)
  await db.commit()
  preview_url=await media.access_url(c.asset_id,user.id)
 except StorageError as exc:
  await db.rollback()
  raise HTTPException(503,'Media storage is unavailable') from exc
 return {'candidate_id':c.id,'preview_url':preview_url,'expires_at':c.expires_at}

@router.post('/main-image/upload',status_code=201)
async def upload_main_image(file:UploadFile=File(...),db=Depends(get_async_session),user=Depends(get_current_user),media:MediaService=Depends(get_media_service)):
 data=await file.read()
 asset=await media.create_asset(owner_user_id=user.id,category='product_image',data=data,content_type=file.content_type or 'application/octet-stream',filename=file.filename or 'upload.bin')
 await db.commit()
 return {'asset_id':asset.id,'url':await media.access_url(asset.id,user.id)}

@router.post('/packaging-images/generate', response_model=PackagingImageCandidateResponse, status_code=201)
async def generate_packaging_image(body: PackagingImageGenerateRequest, db=Depends(get_async_session), user=Depends(get_current_user)):
 await prepare(db, user, body)
 media = get_media_service(db)
 try:
  reference = await media.data_uri(body.main_image_asset_id, user.id)
  url = await generate_image(build_packaging_image_prompt(body, body.prompt), ref_image_url=reference)
  asset = await media.create_from_remote(owner_user_id=user.id, category='product_image', source_url=url, filename=f'packaging-candidate-{user.id}.png', fetch=_fetch_provider_media, source_provider='image-provider')
  await db.commit()
  return {'candidate_id': asset.id, 'asset_id': asset.id, 'preview_url': await media.access_url(asset.id, user.id), 'expires_at': None}
 except StorageError as exc:
  await db.rollback(); raise HTTPException(503, 'Media storage is unavailable') from exc

@router.post('',response_model=ProductResponse,status_code=201)
async def create(body:ProductCreate,db=Depends(get_async_session),user=Depends(get_current_user)):
    attrs=await prepare(db,user,body); source='asset'; url=''
    if body.main_image_asset_id and body.main_image_candidate_id:
        raise HTTPException(422,'choose asset, upload or candidate')
    if body.main_image_asset_id:
        asset = (await db.execute(select(MediaAsset).where(
            MediaAsset.id == body.main_image_asset_id,
            MediaAsset.owner_user_id == user.id,
            MediaAsset.status == 'available',
            MediaAsset.category == 'product_image',
        ))).scalar_one_or_none()
        if not asset: raise HTTPException(404,'Main image asset not found')
        url,source = '', 'asset'
    if body.main_image_candidate_id and body.main_image_asset_id: raise HTTPException(422,'choose upload or candidate')
    if body.main_image_candidate_id:
        c=await consume_candidate(db,user.id,body.main_image_candidate_id)
        if not c: raise HTTPException(422,'Invalid main image candidate')
        body.main_image_asset_id=c.asset_id; url,source='','ai'
    if not url and not body.main_image_asset_id: raise HTTPException(422,'Main image required')
    packaging_assets = await owned_packaging_assets(db, user.id, body.packaging_image_asset_ids)
    data=body.model_dump(exclude={'main_image_candidate_id', 'packaging_image_asset_ids'}); data['attributes']=attrs
    p=Product(user_id=user.id,main_image_url=url,main_image_source=source,**data); db.add(p)
    for sort_order, asset in enumerate(packaging_assets):
        db.add(ProductPackagingImage(product_id=p.id, asset_id=asset.id, source='upload', sort_order=sort_order))
    await db.commit(); await db.refresh(p); return p

@router.get('',response_model=PaginatedProducts)
async def listing(category_id=None,search=None,page:int=1,page_size:int=20,db=Depends(get_async_session),user=Depends(get_current_user)):
 q=select(Product).where(Product.user_id==user.id).options(selectinload(Product.packaging_images))
 if category_id:q=q.where(Product.category_id==category_id)
 if search:q=q.where(Product.name.ilike('%'+search.replace('%','\\%').replace('_','\\_')+'%',escape='\\'))
 total=(await db.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
 items=(await db.execute(q.offset((page-1)*page_size).limit(page_size))).scalars().all()
 return {'items':items,'total':total,'page':page,'page_size':page_size}

async def owned(db,user,id):
 p=(await db.execute(select(Product).where(Product.id==id,Product.user_id==user.id).options(selectinload(Product.packaging_images)))).scalar_one_or_none()
 if not p:raise HTTPException(404,'Product not found')
 return p

@router.get('/{id}',response_model=ProductResponse)
async def get(id,db=Depends(get_async_session),user=Depends(get_current_user)):return await owned(db,user,id)
@router.put('/{id}',response_model=ProductResponse)
async def update(id,body:ProductUpdate,db=Depends(get_async_session),user=Depends(get_current_user)):
 p=await owned(db,user,id); attrs=await prepare(db,user,body)
 if body.main_image_asset_id:
  asset=(await db.execute(select(MediaAsset).where(MediaAsset.id==body.main_image_asset_id,MediaAsset.owner_user_id==user.id,MediaAsset.status=='available',MediaAsset.category=='product_image'))).scalar_one_or_none()
  if not asset: raise HTTPException(404,'Main image asset not found')
  p.main_image_asset_id=asset.id; p.main_image_url=''; p.main_image_source='asset'
 packaging_assets = await owned_packaging_assets(db, user.id, body.packaging_image_asset_ids)
 data=body.model_dump(exclude={'main_image_candidate_id','main_image_asset_id','packaging_image_asset_ids'})
 for k,v in data.items(): setattr(p,k,v)
 if body.main_image_candidate_id and body.main_image_asset_id: raise HTTPException(422,'choose upload or candidate')
 if body.main_image_candidate_id:
  c=await consume_candidate(db,user.id,body.main_image_candidate_id)
  if not c: raise HTTPException(422,'Invalid main image candidate')
  p.main_image_asset_id,p.main_image_url,p.main_image_source=c.asset_id,'','ai'
 await db.execute(sql_delete(ProductPackagingImage).where(ProductPackagingImage.product_id == p.id))
 for sort_order, asset in enumerate(packaging_assets):
  db.add(ProductPackagingImage(product_id=p.id, asset_id=asset.id, source='upload', sort_order=sort_order))
 p.attributes=attrs; await db.commit(); await db.refresh(p); return p
@router.delete('/{id}',status_code=204)
async def delete(id,db=Depends(get_async_session),user=Depends(get_current_user)):
 p=await owned(db,user,id); await db.delete(p); await db.commit()
