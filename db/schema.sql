-- 香水短视频生成应用 — 数据库 DDL
-- PostgreSQL, 在 agent-infra 中创建独立 database:
--   docker compose exec postgres createdb -U agent perfume_video

-- 产品表
CREATE TABLE products (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            VARCHAR(255) NOT NULL,
    top_note        TEXT,
    middle_note     TEXT,
    base_note       TEXT,
    scenarios       JSONB DEFAULT '[]',
    main_image_url  TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 视频任务表
CREATE TABLE video_tasks (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    product_id      UUID NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    type            VARCHAR(20) NOT NULL CHECK (type IN ('promo', 'viral', 'personify')),
    status          VARCHAR(30) NOT NULL DEFAULT 'pending'
                    CHECK (status IN (
                        'pending', 'scripting', 'script_review',
                        'imaging', 'image_review', 'character_review',
                        'video_gen', 'compositing', 'done', 'failed'
                    )),
    current_step    TEXT,
    image_count     INTEGER NOT NULL DEFAULT 4,
    error_message   TEXT,
    result_video_url TEXT,
    celery_task_id  VARCHAR(255),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_video_tasks_product ON video_tasks(product_id);
CREATE INDEX idx_video_tasks_status ON video_tasks(status);
CREATE INDEX idx_video_tasks_type ON video_tasks(type);

-- 脚本表
CREATE TABLE scripts (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id         UUID NOT NULL REFERENCES video_tasks(id) ON DELETE CASCADE UNIQUE,
    content         TEXT NOT NULL,
    edited_content  TEXT,
    image_prompts   JSONB DEFAULT '[]',
    voiceover_text  TEXT,
    status          VARCHAR(20) NOT NULL DEFAULT 'pending_review'
                    CHECK (status IN ('pending_review', 'approved')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 已生成图片表
CREATE TABLE generated_images (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id         UUID NOT NULL REFERENCES video_tasks(id) ON DELETE CASCADE,
    prompt          TEXT NOT NULL,
    image_url       TEXT,
    sort_order      INTEGER NOT NULL DEFAULT 0,
    status          VARCHAR(20) NOT NULL DEFAULT 'pending_review'
                    CHECK (status IN ('pending_review', 'approved', 'rejected')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_generated_images_task ON generated_images(task_id);

-- 爆款视频分析表
CREATE TABLE viral_analyses (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id         UUID NOT NULL REFERENCES video_tasks(id) ON DELETE CASCADE UNIQUE,
    source_url      TEXT NOT NULL,
    original_script TEXT,
    script_structure JSONB,
    shot_list       JSONB DEFAULT '[]',
    style_params    JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 自动更新 updated_at
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_video_tasks_updated_at
    BEFORE UPDATE ON video_tasks
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER trg_scripts_updated_at
    BEFORE UPDATE ON scripts
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER trg_generated_images_updated_at
    BEFORE UPDATE ON generated_images
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- 用户表
CREATE TABLE users (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email           VARCHAR(320) NOT NULL UNIQUE,
    hashed_password VARCHAR(128),
    google_id       VARCHAR(255) UNIQUE,
    role            VARCHAR(20) NOT NULL DEFAULT 'customer' CHECK (role IN ('customer', 'operator')),
    is_active       BOOLEAN NOT NULL DEFAULT true,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_google_id ON users(google_id);

CREATE TRIGGER trg_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();
