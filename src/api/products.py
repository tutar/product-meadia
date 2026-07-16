from fastapi import APIRouter,Depends,HTTPException
from sqlalchemy import select,func
from sqlalchemy.orm import selectinload
from src.database import get_async_session
from src.auth.deps import get_current_user
from src.models.product import Product
from src.schemas.product import ProductCreate,ProductUpdate,ProductResponse,PaginatedProducts,ProductDraft,MainImageCandidateResponse
from src.services.category_service import get_owned_category
from src.services.product_validation import normalize_attributes,AttributeValidationError
from src.services.main_image_candidates import create_candidate,consume_candidate
router=APIRouter(prefix='/products',tags=['products'])

async def prepare(db,user,body):
 c=await get_owned_category(db,user.id,body.category_id,load_attributes=True)
 if not c: raise HTTPException(404,'Category not found')
 if c.template_version!=body.category_template_version: raise HTTPException(409,{'current_version':c.template_version})
 try: attrs=normalize_attributes(c.attributes,body.attributes)
 except AttributeValidationError as e: raise HTTPException(422,e.errors)
 return attrs

@router.post('/main-image/generate',response_model=MainImageCandidateResponse,status_code=201)
async def generate(body:ProductDraft,db=Depends(get_async_session),user=Depends(get_current_user)):
 await prepare(db,user,body); c=await create_candidate(db,user.id,body); await db.commit(); return {'candidate_id':c.id,'preview_url':c.image_url,'expires_at':c.expires_at}

@router.post('',response_model=ProductResponse,status_code=201)
async def create(body:ProductCreate,db=Depends(get_async_session),user=Depends(get_current_user)):
 attrs=await prepare(db,user,body); source='upload'; url=body.main_image_url
 if body.main_image_candidate_id and (body.main_image_url or body.main_image_source): raise HTTPException(422,'choose upload or candidate')
 if body.main_image_url and body.main_image_source != 'upload': raise HTTPException(422,'main_image_source upload required')
 if body.main_image_candidate_id:
  c=await consume_candidate(db,user.id,body.main_image_candidate_id)
  if not c: raise HTTPException(422,'Invalid main image candidate')
  url,source=c.image_url,'ai'
 if not url: raise HTTPException(422,'Main image required')
 data=body.model_dump(exclude={'main_image_candidate_id','main_image_url','main_image_source'}); data['attributes']=attrs
 p=Product(user_id=user.id,main_image_url=url,main_image_source=source,**data); db.add(p); await db.commit(); await db.refresh(p); return p

@router.get('',response_model=PaginatedProducts)
async def listing(category_id=None,search=None,page:int=1,page_size:int=20,db=Depends(get_async_session),user=Depends(get_current_user)):
 q=select(Product).where(Product.user_id==user.id)
 if category_id:q=q.where(Product.category_id==category_id)
 if search:q=q.where(Product.name.ilike('%'+search.replace('%','\\%').replace('_','\\_')+'%',escape='\\'))
 total=(await db.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
 items=(await db.execute(q.offset((page-1)*page_size).limit(page_size))).scalars().all()
 return {'items':items,'total':total,'page':page,'page_size':page_size}

async def owned(db,user,id):
 p=(await db.execute(select(Product).where(Product.id==id,Product.user_id==user.id))).scalar_one_or_none()
 if not p:raise HTTPException(404,'Product not found')
 return p

@router.get('/{id}',response_model=ProductResponse)
async def get(id,db=Depends(get_async_session),user=Depends(get_current_user)):return await owned(db,user,id)
@router.put('/{id}',response_model=ProductResponse)
async def update(id,body:ProductUpdate,db=Depends(get_async_session),user=Depends(get_current_user)):
 p=await owned(db,user,id); attrs=await prepare(db,user,body)
 data=body.model_dump(exclude={'main_image_candidate_id','main_image_url','main_image_source'})
 for k,v in data.items(): setattr(p,k,v)
 if body.main_image_candidate_id and (body.main_image_url or body.main_image_source): raise HTTPException(422,'choose upload or candidate')
 if body.main_image_url and body.main_image_source != 'upload': raise HTTPException(422,'main_image_source upload required')
 if body.main_image_candidate_id:
  c=await consume_candidate(db,user.id,body.main_image_candidate_id)
  if not c: raise HTTPException(422,'Invalid main image candidate')
  p.main_image_url,p.main_image_source=c.image_url,'ai'
 elif body.main_image_url:
  p.main_image_url,p.main_image_source=body.main_image_url,'upload'
 p.attributes=attrs; await db.commit(); await db.refresh(p); return p
@router.delete('/{id}',status_code=204)
async def delete(id,db=Depends(get_async_session),user=Depends(get_current_user)):
 p=await owned(db,user,id); await db.delete(p); await db.commit()
