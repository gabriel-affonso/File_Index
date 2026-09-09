from __future__ import annotations
from database.duckdb import Catalog

class ExplorerService:
    def __init__(self, catalog: Catalog): self.catalog = catalog
    def search(self, query: str, category: str | None = None):
        q = f'%{query.lower()}%'; condition = '' if not category else ' AND f.file_category = ?'; params = [q] * 8 + ([category] if category else [])
        return self.catalog.conn.execute(f'''SELECT DISTINCT f.file_id, f.filename, f.path, f.extension, f.file_category, f.size_bytes,
          CASE WHEN lower(f.filename) LIKE ? THEN 100 WHEN lower(f.directory) LIKE ? THEN 50 WHEN lower(coalesce(d.text_content,'')) LIKE ? THEN 20 WHEN EXISTS (SELECT 1 FROM dataset_columns dc JOIN sheets s ON s.sheet_id=dc.sheet_id JOIN datasets ds ON ds.dataset_id=s.dataset_id WHERE ds.file_id=f.file_id AND lower(dc.column_name) LIKE ?) THEN 70 ELSE 0 END score
          FROM files f LEFT JOIN document_content d ON d.file_id=f.file_id WHERE f.deleted=FALSE AND (lower(f.filename) LIKE ? OR lower(f.directory) LIKE ? OR lower(coalesce(d.text_content,'')) LIKE ? OR EXISTS (SELECT 1 FROM dataset_columns dc JOIN sheets s ON s.sheet_id=dc.sheet_id JOIN datasets ds ON ds.dataset_id=s.dataset_id WHERE ds.file_id=f.file_id AND lower(dc.column_name) LIKE ?)){condition} ORDER BY score DESC, f.filename''', params).fetchall()
    def details(self, file_id):
        return self.catalog.conn.execute('SELECT f.*, d.text_content, d.page_count FROM files f LEFT JOIN document_content d ON f.file_id=d.file_id WHERE f.file_id=?', [file_id]).fetchone()
    def dataset_preview(self, file_id):
        return self.catalog.conn.execute('SELECT s.sheet_name,s.row_count,s.column_count, string_agg(dc.column_name, \' | \') FROM datasets ds JOIN sheets s ON s.dataset_id=ds.dataset_id LEFT JOIN dataset_columns dc ON dc.sheet_id=s.sheet_id WHERE ds.file_id=? GROUP BY ALL', [file_id]).fetchall()
    def tags(self, file_id):
        return self.catalog.conn.execute('SELECT t.name FROM tags t JOIN file_tags ft ON ft.tag_id=t.tag_id WHERE ft.file_id=?', [file_id]).fetchall()
    def add_tag(self, file_id, name):
        name = name.strip().lstrip('#'); tag_id=self.catalog.scalar('SELECT tag_id FROM tags WHERE name=?',[name])
        if not tag_id: tag_id=self.catalog.new_id(); self.catalog.conn.execute('INSERT INTO tags VALUES (?,?)',[tag_id,name])
        self.catalog.conn.execute('INSERT OR IGNORE INTO file_tags VALUES (?,?)',[file_id,tag_id])
    def create_relation(self, file_id, target_type, label, relation_type='related_to'):
        label = label.strip()
        target_id = self.catalog.scalar('SELECT resource_id FROM resources WHERE resource_type=? AND label=?', [target_type, label])
        if not target_id:
            target_id = self.catalog.new_id()
            self.catalog.conn.execute('INSERT INTO resources VALUES (?, ?, ?, ?)', [target_id, target_type, label, '{}'])
        exists = self.catalog.scalar('SELECT relation_id FROM relations WHERE source_id=? AND target_id=? AND relation_type=?', [file_id, target_id, relation_type])
        if not exists:
            from datetime import datetime
            self.catalog.conn.execute('INSERT INTO relations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)', [self.catalog.new_id(), 'file', file_id, relation_type, target_type, target_id, 'manual', 1.0, datetime.now()])
    def relations(self, file_id):
        return self.catalog.conn.execute('''SELECT r.relation_type, CASE WHEN r.source_id=? THEN coalesce(tf.filename,tr.label) ELSE coalesce(sf.filename,sr.label) END, r.target_type FROM relations r LEFT JOIN files tf ON tf.file_id=r.target_id LEFT JOIN resources tr ON tr.resource_id=r.target_id LEFT JOIN files sf ON sf.file_id=r.source_id LEFT JOIN resources sr ON sr.resource_id=r.source_id WHERE r.source_id=? OR r.target_id=?''',[file_id,file_id,file_id]).fetchall()
    def graph(self, node_id):
        return self.catalog.conn.execute('''SELECT r.relation_id, r.source_id, r.source_type, coalesce(sf.filename,sr.label) source_label, r.relation_type, r.target_id, r.target_type, coalesce(tf.filename,tr.label) target_label FROM relations r LEFT JOIN files sf ON sf.file_id=r.source_id LEFT JOIN resources sr ON sr.resource_id=r.source_id LEFT JOIN files tf ON tf.file_id=r.target_id LEFT JOIN resources tr ON tr.resource_id=r.target_id WHERE r.source_id=? OR r.target_id=? ORDER BY r.created_at DESC''', [node_id,node_id]).fetchall()
    def create_collection(self, name, description=''):
        collection_id=self.catalog.new_id(); self.catalog.conn.execute('INSERT INTO collections VALUES (?, ?, ?, current_timestamp)', [collection_id,name,description]); return collection_id
    def collections(self): return self.catalog.conn.execute('SELECT collection_id,name,description,created_at FROM collections ORDER BY name').fetchall()
    def add_to_collection(self, collection_id, object_type, object_id): self.catalog.conn.execute('INSERT OR IGNORE INTO collection_items VALUES (?, ?, ?)',[collection_id,object_type,object_id])
    def collection_items(self, collection_id):
        return self.catalog.conn.execute('''SELECT ci.object_type,ci.object_id,coalesce(f.filename,r.label,ci.object_id) AS object_label FROM collection_items ci LEFT JOIN files f ON f.file_id=ci.object_id LEFT JOIN resources r ON r.resource_id=ci.object_id WHERE ci.collection_id=? ORDER BY object_label''',[collection_id]).fetchall()
    def remove_from_collection(self, collection_id, object_type, object_id): self.catalog.conn.execute('DELETE FROM collection_items WHERE collection_id=? AND object_type=? AND object_id=?',[collection_id,object_type,object_id])
    def folder_roots(self):
        return self.catalog.conn.execute("SELECT folder_id,path,name,file_count,total_bytes FROM folders WHERE parent_path IS NULL OR parent_path NOT IN (SELECT path FROM folders) ORDER BY name").fetchall()
    def folder_children(self, path):
        folders = self.catalog.conn.execute('SELECT folder_id,path,name,file_count,total_bytes FROM folders WHERE parent_path = ? ORDER BY name', [path]).fetchall()
        files = self.catalog.conn.execute('SELECT file_id,filename,path,file_category,size_bytes FROM files WHERE directory = ? AND deleted = FALSE ORDER BY filename', [path]).fetchall()
        return folders, files
