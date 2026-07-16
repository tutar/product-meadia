# Generic Product Catalog Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace perfume-specific product handling with user-owned category templates, generic products, AI-assisted required main images, registration sample initialization, and immutable task product snapshots.

**Architecture:** PostgreSQL stores relational category templates and JSONB product values; FastAPI services enforce tenant ownership and template validation. Registration emits an outbox event consumed by an idempotent catalog initializer, while video tasks and Agents operate only on a normalized product snapshot. React adds category and product maintenance routes driven by typed API contracts.

**Tech Stack:** Python 3.11, FastAPI, Pydantic 2, SQLAlchemy 2 async, PostgreSQL JSONB, Celery, LangGraph, pytest, React 19, TypeScript 6, Vite 8, Playwright, OpenAPI 3.0.3.

## Global Constraints

- Every category, product, main-image candidate, initialization record, and video task is scoped to the authenticated user; never accept `user_id` from a request body.
- Category attribute types are exactly `text`, `number`, `single_select`, `multi_select`, and `boolean`.
- A product cannot be saved without a confirmed uploaded or AI-generated main image.
- A referenced category cannot be deleted.
- A video task reads an immutable `product_snapshot`; deleting its source product must not break the task.
- Registration and sample copying communicate through a `user.registered` outbox event and an idempotent initializer boundary.
- API definitions belong in `api/openapi.yaml`; complete database DDL belongs in `db/schema.sql`.
- Existing perfume development data may be discarded; do not add legacy `top_note`, `middle_note`, or `base_note` compatibility.
- Run backend tests with `pytest -m 'not integration' -q`; do not require external AI services in the default suite.

---

## File Structure Map

- `db/schema.sql`: authoritative complete DDL, constraints, indexes, trigger order.
- `api/openapi.yaml`: authoritative HTTP request/response and error contract.
- `src/models/category.py`: `Category` and `CategoryAttribute` persistence.
- `src/models/product.py`: tenant-owned generic product persistence.
- `src/models/catalog_initialization.py`: outbox and initialization status persistence.
- `src/models/main_image_candidate.py`: temporary AI image candidates.
- `src/services/category_service.py`: category ownership, template replacement, optimistic locking.
- `src/services/product_validation.py`: typed dynamic attribute normalization.
- `src/services/product_context.py`: task snapshot creation and Agent formatting.
- `src/services/sample_catalog.py`: versioned samples and idempotent initializer.
- `src/services/outbox.py`: event recording and dispatch boundary.
- `src/api/categories.py`: category CRUD.
- `src/api/products.py`: product CRUD and candidate confirmation.
- `src/api/initialization.py`: initialization status query.
- `src/tasks/catalog_tasks.py`: asynchronous outbox consumption and candidate cleanup.
- `src/agents/*_graph.py`: generic-product prompts.
- `frontend/src/api/catalog.ts`: typed catalog API client.
- `frontend/src/pages/CategoriesPage.tsx`: category/template maintenance.
- `frontend/src/pages/ProductsPage.tsx`: product list.
- `frontend/src/pages/ProductFormPage.tsx`: dynamic create/edit form and main-image workflow.

---

### Task 1: Authoritative OpenAPI and Database Contract

**Files:**
- Modify: `api/openapi.yaml`
- Modify: `db/schema.sql`
- Test: `tests/test_contracts.py`

**Interfaces:**
- Produces: tables `categories`, `category_attributes`, `products`, `main_image_candidates`, `outbox_events`, `catalog_initializations`; `video_tasks.product_snapshot`; OpenAPI schemas `Category`, `CategoryAttribute`, `Product`, `MainImageCandidate`, `InitializationStatus`.
- Consumes: existing `users` and `video_tasks` concepts.

- [ ] **Step 1: Write failing contract tests**

```python
# tests/test_contracts.py
from pathlib import Path
import yaml

ROOT = Path(__file__).parents[1]

def test_openapi_exposes_catalog_contract():
    doc = yaml.safe_load((ROOT / "api/openapi.yaml").read_text())
    assert "/categories" in doc["paths"]
    assert "/products/main-image/generate" in doc["paths"]
    assert "/initialization-status" in doc["paths"]
    assert set(doc["components"]["schemas"]["AttributeType"]["enum"]) == {
        "text", "number", "single_select", "multi_select", "boolean"
    }

def test_schema_contains_generic_catalog_and_snapshot():
    ddl = (ROOT / "db/schema.sql").read_text()
    for table in ("categories", "category_attributes", "main_image_candidates", "outbox_events", "catalog_initializations"):
        assert f"CREATE TABLE {table}" in ddl
    assert "product_snapshot JSONB" in ddl
    assert "top_note" not in ddl
```

- [ ] **Step 2: Run tests and verify the old contract fails**

Run: `pytest tests/test_contracts.py -v`
Expected: FAIL because category paths/tables and `product_snapshot` do not exist.

- [ ] **Step 3: Replace the product portion of `db/schema.sql` with the complete generic DDL**

Define `update_updated_at()` before any trigger. Use UUID primary keys, `ON DELETE CASCADE` from user to private catalog data, `ON DELETE RESTRICT` from product to category, and `ON DELETE SET NULL` from task to product. Add:

```sql
CREATE TABLE categories (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name VARCHAR(255) NOT NULL,
  description TEXT,
  template_version INTEGER NOT NULL DEFAULT 1 CHECK (template_version > 0),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (user_id, name)
);

CREATE TABLE category_attributes (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  category_id UUID NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
  key VARCHAR(100) NOT NULL,
  label VARCHAR(255) NOT NULL,
  type VARCHAR(20) NOT NULL CHECK (type IN ('text','number','single_select','multi_select','boolean')),
  required BOOLEAN NOT NULL DEFAULT false,
  options JSONB NOT NULL DEFAULT '[]',
  sort_order INTEGER NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (category_id, key)
);
```

Define generic `products` with `user_id`, `category_id`, `description`, `selling_points`, `scenarios`, required `main_image_url`, `main_image_source`, `attributes`, and `category_template_version`. Define candidates with owner, URL, expiry, and `used_at`; outbox rows with event type/payload/attempt timestamps; initialization rows unique on `(user_id, sample_version)`. Add user/category/status indexes and update triggers.

- [ ] **Step 4: Expand `api/openapi.yaml`**

Define all paths from the design, including pagination/filter parameters, category templates submitted atomically, field-level validation errors, `409` template conflicts, and `409` referenced-category deletion. `MainImageGenerateRequest` must accept a product draft without `user_id`; `ProductCreate` must accept either `main_image_url` with source `upload` or `main_image_candidate_id`.

- [ ] **Step 5: Run contract tests**

Run: `pytest tests/test_contracts.py -v`
Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add api/openapi.yaml db/schema.sql tests/test_contracts.py
git commit -m "feat: define generic catalog contracts"
```

---

### Task 2: Catalog Persistence Models and Typed Validation

**Files:**
- Create: `src/models/category.py`
- Create: `src/models/main_image_candidate.py`
- Create: `src/models/catalog_initialization.py`
- Modify: `src/models/product.py`
- Modify: `src/models/task.py`
- Modify: `src/models/__init__.py`
- Create: `src/services/__init__.py`
- Create: `src/services/product_validation.py`
- Modify: `tests/test_models/test_models.py`
- Create: `tests/test_services/test_product_validation.py`

**Interfaces:**
- Produces: `normalize_attributes(definitions: list[CategoryAttribute], values: dict[str, object]) -> dict[str, object]`.
- Produces: ORM classes matching Task 1 DDL.

- [ ] **Step 1: Write failing model and validation tests**

```python
def test_product_is_generic_and_tenant_owned():
    assert hasattr(Product, "user_id") and hasattr(Product, "attributes")
    assert not hasattr(Product, "top_note")
    assert hasattr(VideoTask, "product_snapshot")

def test_normalize_attributes_supports_all_types():
    definitions = [
        Stub("title", "text", True, []), Stub("weight", "number", True, []),
        Stub("color", "single_select", True, ["red", "blue"]),
        Stub("tags", "multi_select", False, ["new", "gift"]),
        Stub("recyclable", "boolean", False, []),
    ]
    assert normalize_attributes(definitions, {
        "title": "Cup", "weight": 2.5, "color": "red",
        "tags": ["gift", "gift"], "recyclable": True,
    }) == {"title": "Cup", "weight": 2.5, "color": "red", "tags": ["gift"], "recyclable": True}
```

Also assert missing required values, unknown keys, invalid options, booleans passed as numbers, and malformed multi-select values raise `AttributeValidationError(errors={key: message})`.

- [ ] **Step 2: Verify failures**

Run: `pytest tests/test_models/test_models.py tests/test_services/test_product_validation.py -v`
Expected: FAIL on missing models and validator.

- [ ] **Step 3: Implement focused ORM classes**

Use `UUIDMixin`/`TimestampMixin`, PostgreSQL `UUID`/`JSONB`, explicit foreign keys and relationships. Set `VideoTask.product_id` nullable with `SET NULL`, add non-null `user_id`, and add non-null `product_snapshot` with no mutable default.

- [ ] **Step 4: Implement strict normalization**

```python
class AttributeValidationError(ValueError):
    def __init__(self, errors: dict[str, str]):
        self.errors = errors
        super().__init__("Invalid product attributes")

def normalize_attributes(definitions, values):
    by_key = {item.key: item for item in definitions}
    errors = {key: "Unknown attribute" for key in values.keys() - by_key.keys()}
    normalized = {}
    # Validate required empty values, exact Python types, configured options,
    # and stable de-duplication for multi-select. Raise once with all errors.
    if errors:
        raise AttributeValidationError(errors)
    return normalized
```

- [ ] **Step 5: Run tests**

Run: `pytest tests/test_models/test_models.py tests/test_services/test_product_validation.py -v`
Expected: all passed.

- [ ] **Step 6: Commit**

```bash
git add src/models src/services tests/test_models tests/test_services
git commit -m "feat: add generic catalog models and validation"
```

---

### Task 3: Tenant-Safe Category API

**Files:**
- Create: `src/schemas/category.py`
- Create: `src/services/category_service.py`
- Create: `src/api/categories.py`
- Modify: `src/main.py`
- Create: `tests/test_api/test_categories.py`

**Interfaces:**
- Produces: `get_owned_category(db, user_id, category_id, *, load_attributes=False) -> Category | None`.
- Produces: `replace_template(db, category, expected_version, attributes) -> Category`.

- [ ] **Step 1: Write API tests**

Test create/list/get/update/delete; duplicate names; cross-user GET/PUT/DELETE returning 404; option validation; version mismatch returning 409 with `current_version`; referenced category returning 409 with `product_count`.

```python
response = await client.put(f"/api/v1/categories/{category.id}", headers=auth, json={
    "name": "Electronics", "description": "Devices", "template_version": 1,
    "attributes": [{"key": "color", "label": "Color", "type": "single_select", "required": True,
                    "options": ["black", "white"], "sort_order": 0}],
})
assert response.status_code == 200
assert response.json()["template_version"] == 2
```

- [ ] **Step 2: Verify tests fail**

Run: `pytest tests/test_api/test_categories.py -v`
Expected: FAIL because router and schemas do not exist.

- [ ] **Step 3: Implement schemas and service**

Use a discriminated validation rule in `CategoryAttributeInput`: selection types require unique non-empty options; other types require `[]`. Replace all template rows and increment the version in one transaction after matching `expected_version`.

- [ ] **Step 4: Implement and register router**

Every query must include `Category.user_id == user.id`. Catch uniqueness violations as 409. Count products before delete and return structured conflict detail. Register with `app.include_router(categories.router, prefix="/api/v1")`.

- [ ] **Step 5: Run tests**

Run: `pytest tests/test_api/test_categories.py -v`
Expected: all passed.

- [ ] **Step 6: Commit**

```bash
git add src/schemas/category.py src/services/category_service.py src/api/categories.py src/main.py tests/test_api/test_categories.py
git commit -m "feat: add tenant-safe category API"
```

---

### Task 4: Generic Product CRUD and AI Main-Image Candidates

**Files:**
- Modify: `src/schemas/product.py`
- Modify: `src/api/products.py`
- Create: `src/services/main_image_candidates.py`
- Create: `src/tasks/catalog_tasks.py`
- Modify: `src/tasks/celery_app.py`
- Create: `tests/test_api/test_products.py`
- Create: `tests/test_services/test_main_image_candidates.py`

**Interfaces:**
- Consumes: `normalize_attributes`, `get_owned_category`, existing `generate_image(prompt: str) -> str`.
- Produces: `build_main_image_prompt(draft: ProductDraft) -> str` and `consume_candidate(db, user_id, candidate_id) -> MainImageCandidate`.

- [ ] **Step 1: Write failing tests**

Cover product create/list/filter/get/update/delete, user isolation, dynamic validation, stale template 409, missing image 422, candidate ownership/expiry/single-use, and deletion preserving a task snapshot. Mock `src.services.main_image_candidates.generate_image`.

```python
with patch("src.services.main_image_candidates.generate_image", AsyncMock(return_value="https://img/cup.png")):
    generated = await client.post("/api/v1/products/main-image/generate", headers=auth, json=draft)
assert generated.status_code == 201
candidate_id = generated.json()["candidate_id"]
created = await client.post("/api/v1/products", headers=auth, json={**draft, "main_image_candidate_id": candidate_id})
assert created.json()["main_image_source"] == "ai"
```

- [ ] **Step 2: Verify tests fail**

Run: `pytest tests/test_api/test_products.py tests/test_services/test_main_image_candidates.py -v`
Expected: FAIL against perfume-only CRUD.

- [ ] **Step 3: Implement schemas and candidate service**

Define typed `ProductDraft`, `ProductCreate`, `ProductUpdate`, `ProductResponse`, and paginated response. Build prompts from normalized user data without perfume language. Candidate expiry is 24 hours; consume by setting `used_at` in the same product transaction.

- [ ] **Step 4: Replace product router**

Every query includes `Product.user_id == user.id`. Eager-load category definitions for validation. Search uses escaped case-insensitive containment; category filtering also verifies ownership. Delete product normally; task FK behavior preserves snapshots.

- [ ] **Step 5: Add candidate cleanup task**

Implement `cleanup_expired_main_image_candidates` to delete only unused expired rows and schedule it in Celery beat. Do not delete external assets inside the database transaction; expose a separate best-effort asset cleanup hook.

- [ ] **Step 6: Run tests**

Run: `pytest tests/test_api/test_products.py tests/test_services/test_main_image_candidates.py -v`
Expected: all passed.

- [ ] **Step 7: Commit**

```bash
git add src/schemas/product.py src/api/products.py src/services/main_image_candidates.py src/tasks tests/test_api/test_products.py tests/test_services/test_main_image_candidates.py
git commit -m "feat: add generic products and AI main images"
```

---

### Task 5: Outbox-Driven Sample Catalog Initialization

**Files:**
- Create: `src/services/outbox.py`
- Create: `src/services/sample_catalog.py`
- Create: `src/api/initialization.py`
- Modify: `src/auth/routes.py`
- Modify: `src/main.py`
- Modify: `src/tasks/catalog_tasks.py`
- Create: `tests/test_services/test_sample_catalog.py`
- Modify: `tests/test_flow.py`

**Interfaces:**
- Produces: `record_event(db, event_type: str, aggregate_id: UUID, payload: dict) -> OutboxEvent`.
- Produces: `SampleCatalogInitializer.initialize(db, user_id: UUID, sample_version: int) -> CatalogInitialization`.

- [ ] **Step 1: Write failing outbox and idempotency tests**

Assert password registration and first-time Google OAuth each create exactly one `user.registered` event in the user transaction. Assert processing the same event twice produces one initialization row and one copy of each sample. Assert a failed initialization records `failed` and can converge to `completed` on retry.

- [ ] **Step 2: Verify tests fail**

Run: `pytest tests/test_services/test_sample_catalog.py tests/test_flow.py -v`
Expected: FAIL because registration commits directly without outbox.

- [ ] **Step 3: Implement event boundary and samples**

Keep sample definitions in `src/services/sample_catalog.py` as immutable versioned data with stable keys. Include at least perfume, electronics, and food examples, each with a confirmed bundled or deterministic placeholder main image so initialization never calls external AI.

```python
SAMPLE_VERSION = 1
SAMPLE_CATEGORIES = ({
    "key": "sample-electronics", "name": "Electronics",
    "attributes": ({"key": "color", "label": "Color", "type": "single_select",
                    "required": True, "options": ("black", "white")},),
},)
```

- [ ] **Step 4: Refactor registration transaction**

Create the user and outbox row before one `db.commit()`. Do this in a shared helper used by password and Google registration. Never import `SampleCatalogInitializer` from auth routes.

- [ ] **Step 5: Add dispatcher task and status API**

Use row locking/attempt metadata to claim pending events. Call only the initializer interface, mark processed on success, and retain error/next attempt on failure. `/initialization-status` returns `pending` until a version row completes.

- [ ] **Step 6: Run tests**

Run: `pytest tests/test_services/test_sample_catalog.py tests/test_flow.py -v`
Expected: all passed.

- [ ] **Step 7: Commit**

```bash
git add src/services/outbox.py src/services/sample_catalog.py src/api/initialization.py src/auth/routes.py src/main.py src/tasks/catalog_tasks.py tests
git commit -m "feat: initialize user catalogs through outbox events"
```

---

### Task 6: Immutable Product Snapshots and Tenant-Safe Task APIs

**Files:**
- Create: `src/services/product_context.py`
- Modify: `src/schemas/task.py`
- Modify: `src/api/tasks.py`
- Modify: `src/tasks/video_tasks.py`
- Create: `tests/test_services/test_product_context.py`
- Modify: `tests/test_flow.py`

**Interfaces:**
- Produces: `build_product_snapshot(product: Product, category: Category) -> dict`.
- Produces: `format_product_context(snapshot: dict) -> str`.
- Consumes: snapshot dictionary in `VideoAgentState.product_info`.

- [ ] **Step 1: Write snapshot and ownership tests**

Assert snapshot contains category identity, product base fields, main image, and only active attributes ordered by `sort_order`. Assert product edits/deletion do not change task responses or retry state. Add cross-user list/detail/script/image/resume/video tests so every task subresource is tenant-safe.

- [ ] **Step 2: Verify tests fail**

Run: `pytest tests/test_services/test_product_context.py tests/test_flow.py -v`
Expected: FAIL because tasks query products/tasks without owner and workers reload the product.

- [ ] **Step 3: Implement deterministic snapshot formatting**

```python
def format_product_context(snapshot: dict) -> str:
    lines = [f"Product: {snapshot['name']}", f"Category: {snapshot['category']['name']}"]
    lines.extend(f"{item['label']}: {format_value(item['type'], item['value'])}"
                 for item in snapshot["attributes"])
    return "\n".join(lines)
```

Reject missing snapshot version or malformed data at task creation, not inside an Agent.

- [ ] **Step 4: Make all task APIs owner-scoped**

Store `VideoTask.user_id` and snapshot in the create transaction. Add `VideoTask.user_id == user.id` to list/count/detail and every subresource query. Return snapshot product name/image in `TaskResponse`.

- [ ] **Step 5: Make workers snapshot-only**

Remove `session.get(Product, task.product_id)` from `video_tasks.py`. Populate graph state from `task.product_snapshot`, including retries and manual resume.

- [ ] **Step 6: Run tests**

Run: `pytest tests/test_services/test_product_context.py tests/test_flow.py -v`
Expected: all passed.

- [ ] **Step 7: Commit**

```bash
git add src/services/product_context.py src/schemas/task.py src/api/tasks.py src/tasks/video_tasks.py tests
git commit -m "feat: snapshot products for tenant-safe video tasks"
```

---

### Task 7: Generalize All Agent Prompts

**Files:**
- Modify: `src/agents/state.py`
- Modify: `src/agents/promo_graph.py`
- Modify: `src/agents/viral_graph.py`
- Modify: `src/agents/personify_graph.py`
- Modify: `tests/test_agents/test_promo_graph.py`
- Modify: `tests/test_agents/test_viral_graph.py`
- Modify: `tests/test_agents/test_personify_graph.py`
- Create: `tests/test_agents/test_generic_products.py`

**Interfaces:**
- Consumes: normalized snapshot as `VideoAgentState.product_info` and `format_product_context(snapshot)`.
- Produces: category-neutral scripts/image prompts for all graph types.

- [ ] **Step 1: Add failing parametrized generic-product tests**

Use perfume, electronics, and food snapshots. Mock LLM/media tools, capture prompts, and assert each contains actual category/name/attributes while perfume-only terms are absent for non-perfume products.

```python
@pytest.mark.parametrize("category,forbidden", [("Electronics", "top notes"), ("Food", "perfume bottle")])
async def test_prompts_follow_product_context(category, forbidden):
    prompt = await capture_promo_prompt(snapshot_for(category))
    assert category in prompt
    assert forbidden not in prompt.lower()
```

- [ ] **Step 2: Verify failures**

Run: `pytest tests/test_agents -v`
Expected: FAIL on perfume-specific prompt text and field access.

- [ ] **Step 3: Rewrite prompts and field access**

Promo structure is hook → need/scene → selling points → attribute evidence → CTA. Viral adapts the reference structure using serialized product context. Personify derives character and first-person voice from category, appearance, selling points, and attributes. Replace fixed video prompts such as “luxury perfume advertisement” with snapshot-derived style.

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_agents -v`
Expected: all passed.

- [ ] **Step 5: Commit**

```bash
git add src/agents tests/test_agents
git commit -m "feat: generalize video agents for any product"
```

---

### Task 8: Typed Frontend Catalog Client and Category Management

**Files:**
- Create: `frontend/src/api/catalog.ts`
- Create: `frontend/src/pages/CategoriesPage.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/i18n/zh.json`
- Modify: `frontend/src/i18n/en.json`
- Modify: `frontend/src/styles/design.css`
- Create: `frontend/tests/categories.spec.ts`

**Interfaces:**
- Produces: TypeScript `AttributeType`, `CategoryAttribute`, `Category`, `CategoryInput`; `catalogApi.listCategories/createCategory/updateCategory/deleteCategory`.

- [ ] **Step 1: Write failing Playwright test**

Mock category endpoints. Verify navigation, create/edit form, all five field types, conditional options editor, reorder controls, version submitted on edit, and disabled deletion with product count.

- [ ] **Step 2: Run test to verify missing page**

Run: `cd frontend && npx playwright test tests/categories.spec.ts`
Expected: FAIL because `/categories` is not routed.

- [ ] **Step 3: Implement typed client and category page**

Avoid `any`. Keep API request functions in `catalog.ts`; keep row editing helpers inside `CategoriesPage.tsx`. Submit the entire ordered attribute array atomically. Translate backend field errors and 409 version conflicts.

- [ ] **Step 4: Register route, navigation, translations, and focused styles**

Add `/categories`, a header link, Chinese and English catalog strings, responsive template editor rows, and accessible labels/buttons.

- [ ] **Step 5: Run focused checks**

Run: `cd frontend && npx playwright test tests/categories.spec.ts && npm run lint && npm run build`
Expected: category spec passes; lint/build exit 0 with no new warnings.

- [ ] **Step 6: Commit**

```bash
git add frontend/src frontend/tests/categories.spec.ts
git commit -m "feat: add category template management UI"
```

---

### Task 9: Product Management and AI Main-Image Workflow

**Files:**
- Extend: `frontend/src/api/catalog.ts`
- Create: `frontend/src/pages/ProductsPage.tsx`
- Create: `frontend/src/pages/ProductFormPage.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/i18n/zh.json`
- Modify: `frontend/src/i18n/en.json`
- Modify: `frontend/src/styles/design.css`
- Create: `frontend/tests/products.spec.ts`

**Interfaces:**
- Produces: `Product`, `ProductDraft`, `MainImageCandidate`; product CRUD and `generateMainImage` client calls.
- Consumes: category types/API from Task 8.

- [ ] **Step 1: Write failing product E2E tests**

Mock list/categories/product/candidate endpoints. Test search/filter, dynamic fields for all five types, required errors, category-switch confirmation and attribute clearing, uploaded-image preview, AI candidate preview/regenerate/confirm, edit, and delete task-count warning.

- [ ] **Step 2: Verify tests fail**

Run: `cd frontend && npx playwright test tests/products.spec.ts`
Expected: FAIL because product routes do not exist.

- [ ] **Step 3: Implement product list and typed dynamic form**

Routes are `/products`, `/products/new`, `/products/:id/edit`. Product save remains disabled until an uploaded preview or confirmed AI candidate exists. Do not silently retain attributes when category changes.

- [ ] **Step 4: Implement AI candidate state machine**

Use explicit states `idle | generating | preview | confirmed | error`. Regenerate invalidates only the client selection, not the draft. Submit `main_image_candidate_id` only after confirmation; uploaded images submit `main_image_url` and `main_image_source: "upload"`.

- [ ] **Step 5: Run focused checks**

Run: `cd frontend && npx playwright test tests/products.spec.ts && npm run lint && npm run build`
Expected: product spec passes; lint/build exit 0 with no new warnings.

- [ ] **Step 6: Commit**

```bash
git add frontend/src frontend/tests/products.spec.ts
git commit -m "feat: add product management and AI main images"
```

---

### Task 10: Initialization UX and Task-Creation Integration

**Files:**
- Modify: `frontend/src/api/catalog.ts`
- Modify: `frontend/src/pages/ProductsPage.tsx`
- Modify: `frontend/src/pages/CreateTaskPage.tsx`
- Modify: `frontend/src/pages/DashboardPage.tsx`
- Modify: `frontend/src/i18n/zh.json`
- Modify: `frontend/src/i18n/en.json`
- Create: `frontend/tests/catalog-integration.spec.ts`

**Interfaces:**
- Consumes: `InitializationStatus`, generic `Product`, snapshot-backed task response.
- Produces: pending/failed sample initialization notices and generic task product selection.

- [ ] **Step 1: Write failing integration E2E test**

Mock pending then completed initialization, verify non-blocking notice and manual create action. Verify task selector shows generic name/category/image and successful creation. Verify deleted products do not remove existing dashboard tasks whose snapshot supplies display data.

- [ ] **Step 2: Verify failure**

Run: `cd frontend && npx playwright test tests/catalog-integration.spec.ts`
Expected: FAIL because initialization and snapshot fields are not rendered.

- [ ] **Step 3: Implement initialization status and generic task integration**

Poll only while status is `pending`, stop on `completed` or `failed`, and clean up timers on unmount. Failed initialization presents retry status text but never disables category/product creation. Remove perfume wording and `any` product types from task creation.

- [ ] **Step 4: Run frontend suite**

Run: `cd frontend && npx playwright test && npm run lint && npm run build`
Expected: all Playwright tests pass; lint/build exit 0 with no new warnings.

- [ ] **Step 5: Commit**

```bash
git add frontend/src frontend/tests/catalog-integration.spec.ts
git commit -m "feat: integrate catalog initialization and video tasks"
```

---

### Task 11: Full Verification and Documentation Consistency

**Files:**
- Modify only if verification finds drift: `api/openapi.yaml`, `db/schema.sql`, `frontend/README.md`
- Test: all non-integration backend and frontend tests.

**Interfaces:**
- Consumes: every interface produced by Tasks 1–10.
- Produces: a verified implementation with no perfume-specific runtime coupling.

- [ ] **Step 1: Scan for legacy coupling**

Run: `rg -n -i 'top_note|middle_note|base_note|perfume product|perfume bottle|香水短视频' src frontend/src api/openapi.yaml db/schema.sql tests`
Expected: no runtime/API/DDL matches; sample fixtures may contain the word “perfume” only as ordinary category data.

- [ ] **Step 2: Validate contract/implementation naming**

Run: `pytest tests/test_contracts.py -v && rg -n 'main_image_candidate_id|product_snapshot|template_version' api db src frontend/src`
Expected: contract tests pass and each contract field is represented consistently in backend and frontend.

- [ ] **Step 3: Run full local verification**

Run: `pytest -m 'not integration' -q`
Expected: all selected backend tests pass.

Run: `cd frontend && npx playwright test && npm run lint && npm run build`
Expected: all frontend tests pass; build succeeds; no warnings introduced beyond the three recorded baseline warnings.

- [ ] **Step 4: Review git diff and DDL ordering**

Run: `git diff --check main...HEAD && git status --short && sed -n '1,320p' db/schema.sql`
Expected: no whitespace errors, clean worktree, and every trigger function defined before its triggers.

- [ ] **Step 5: Commit any verification-only documentation correction**

If and only if Step 1–4 required documentation/contract corrections:

```bash
git add api/openapi.yaml db/schema.sql frontend/README.md
git commit -m "docs: align generic catalog contracts"
```

Otherwise record that no additional commit is necessary.
