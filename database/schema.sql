CREATE TABLE IF NOT EXISTS files (
    file_id VARCHAR PRIMARY KEY,
    path VARCHAR UNIQUE NOT NULL,
    directory VARCHAR,
    filename VARCHAR NOT NULL,
    extension VARCHAR,
    size_bytes BIGINT,
    created_at TIMESTAMP,
    modified_at TIMESTAMP,
    indexed_at TIMESTAMP,
    file_hash VARCHAR,
    mime_type VARCHAR,
    file_category VARCHAR,
    index_status VARCHAR DEFAULT 'indexed',
    extraction_status VARCHAR DEFAULT 'pending',
    deleted BOOLEAN DEFAULT FALSE,
    excluded BOOLEAN DEFAULT FALSE
);

-- Camada 1 do índice: a estrutura navegável de diretórios.
CREATE TABLE IF NOT EXISTS folders (
    folder_id VARCHAR PRIMARY KEY,
    path VARCHAR UNIQUE NOT NULL,
    parent_path VARCHAR,
    name VARCHAR NOT NULL,
    depth INTEGER NOT NULL,
    file_count BIGINT DEFAULT 0,
    total_bytes BIGINT DEFAULT 0,
    indexed_at TIMESTAMP
);

-- Camada 2: os ficheiros já existentes no catálogo, ligados à pasta.
CREATE TABLE IF NOT EXISTS folder_items (
    folder_id VARCHAR NOT NULL,
    file_id VARCHAR NOT NULL,
    PRIMARY KEY(folder_id, file_id)
);

CREATE TABLE IF NOT EXISTS document_content (
    file_id VARCHAR PRIMARY KEY,
    title VARCHAR,
    text_content VARCHAR,
    page_count INTEGER,
    word_count INTEGER,
    extraction_method VARCHAR
);

CREATE TABLE IF NOT EXISTS document_pages (
    file_id VARCHAR,
    page_number INTEGER,
    text_content VARCHAR,
    PRIMARY KEY(file_id, page_number)
);

CREATE TABLE IF NOT EXISTS datasets (
    dataset_id VARCHAR PRIMARY KEY,
    file_id VARCHAR NOT NULL,
    dataset_type VARCHAR
);

CREATE TABLE IF NOT EXISTS sheets (
    sheet_id VARCHAR PRIMARY KEY,
    dataset_id VARCHAR NOT NULL,
    sheet_name VARCHAR,
    row_count BIGINT,
    column_count INTEGER
);

CREATE TABLE IF NOT EXISTS dataset_columns (
    column_id VARCHAR PRIMARY KEY,
    sheet_id VARCHAR NOT NULL,
    column_name VARCHAR,
    inferred_type VARCHAR,
    null_count BIGINT,
    distinct_count BIGINT
);

CREATE TABLE IF NOT EXISTS tags (tag_id VARCHAR PRIMARY KEY, name VARCHAR UNIQUE NOT NULL);
CREATE TABLE IF NOT EXISTS file_tags (file_id VARCHAR, tag_id VARCHAR, PRIMARY KEY(file_id, tag_id));
CREATE TABLE IF NOT EXISTS collections (collection_id VARCHAR PRIMARY KEY, name VARCHAR UNIQUE NOT NULL, description VARCHAR, created_at TIMESTAMP);
CREATE TABLE IF NOT EXISTS collection_items (collection_id VARCHAR, object_type VARCHAR, object_id VARCHAR, PRIMARY KEY(collection_id, object_type, object_id));
CREATE TABLE IF NOT EXISTS resources (resource_id VARCHAR PRIMARY KEY, resource_type VARCHAR NOT NULL, label VARCHAR NOT NULL, metadata VARCHAR);
CREATE TABLE IF NOT EXISTS relations (
    relation_id VARCHAR PRIMARY KEY, source_type VARCHAR NOT NULL, source_id VARCHAR NOT NULL,
    relation_type VARCHAR NOT NULL, target_type VARCHAR NOT NULL, target_id VARCHAR NOT NULL,
    relation_source VARCHAR DEFAULT 'manual', confidence DOUBLE DEFAULT 1.0, created_at TIMESTAMP
);
