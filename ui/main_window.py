from __future__ import annotations
import os, sys, math, random
from pathlib import Path
from PySide6.QtCore import Qt, QThread, Signal, QUrl, QTimer, QPointF, QRectF
from PySide6.QtGui import QAction, QDesktopServices, QPixmap, QPen, QColor, QBrush, QPainter, QRadialGradient
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QComboBox, QFileDialog, QFrame, QGraphicsItem, QGraphicsLineItem, QGraphicsObject, QGraphicsScene, QGraphicsView, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMessageBox, QProgressBar, QPushButton, QSplitter, QStackedWidget, QTableWidget, QTableWidgetItem, QTextBrowser, QToolBar, QVBoxLayout, QWidget)
from database.duckdb import Catalog
from indexing.indexer import Indexer
from core.services import ExplorerService

class ScanWorker(QThread):
    progress = Signal(int, int, str); finished = Signal(int, int, int)
    def __init__(self, indexer, directory): super().__init__(); self.indexer, self.directory=indexer,directory
    def run(self):
        result=self.indexer.index_directory(self.directory, lambda current, total, name: self.progress.emit(current, total, name)); self.finished.emit(*result)

class DatasetPreview(QWidget):
    def __init__(self):
        super().__init__(); self.frame=None; layout=QVBoxLayout(self); top=QHBoxLayout(); self.sheet=QComboBox(); self.filter=QLineEdit(); self.filter.setPlaceholderText('Filtrar todas as colunas…'); self.filter.textChanged.connect(self.render); top.addWidget(QLabel('Folha:'));top.addWidget(self.sheet);top.addWidget(self.filter,1);layout.addLayout(top);self.table=QTableWidget();self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers);layout.addWidget(self.table,1);self.sheet.currentIndexChanged.connect(self.render)
    def load(self, path):
        import pandas as pd
        self.frames=[]; p=Path(path)
        if p.suffix.lower()=='.csv': self.frames=[('Dados',pd.read_csv(p,nrows=3000,encoding_errors='replace'))]
        else:
            book=pd.ExcelFile(p); self.frames=[(s,pd.read_excel(p,sheet_name=s,nrows=3000)) for s in book.sheet_names]
        self.sheet.blockSignals(True);self.sheet.clear();self.sheet.addItems([x[0] for x in self.frames]);self.sheet.blockSignals(False);self.render()
    def render(self):
        if not self.frames:return
        frame=self.frames[self.sheet.currentIndex()][1].fillna(''); term=self.filter.text().lower().strip()
        if term: frame=frame[frame.astype(str).apply(lambda row: row.str.lower().str.contains(term,regex=False).any(),axis=1)]
        frame=frame.head(1000);self.table.setRowCount(len(frame));self.table.setColumnCount(len(frame.columns));self.table.setHorizontalHeaderLabels([str(c) for c in frame.columns])
        for r,values in enumerate(frame.itertuples(index=False,name=None)):
            for c,value in enumerate(values):self.table.setItem(r,c,QTableWidgetItem(str(value)))
        self.table.resizeColumnsToContents()

class GraphNode(QGraphicsObject):
    def __init__(self, label, color, primary=False):
        super().__init__(); self.label=label;self.color=color;self.primary=primary;self.velocity=QPointF();self.edges=[]
        self.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsMovable | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        self.setCursor(Qt.CursorShape.OpenHandCursor);self.setZValue(2)
    def boundingRect(self): return QRectF(-62,-32,124,64)
    def paint(self,painter,option,widget=None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing); glow=QRadialGradient(0,0,58);glow.setColorAt(0,QColor(self.color.red(),self.color.green(),self.color.blue(),85));glow.setColorAt(1,QColor(0,0,0,0));painter.setBrush(QBrush(glow));painter.setPen(Qt.PenStyle.NoPen);painter.drawEllipse(QRectF(-60,-60,120,120));painter.setBrush(QColor('#060b14'));painter.setPen(QPen(self.color,2.5 if self.primary else 1.5));painter.drawRoundedRect(QRectF(-58,-28,116,56),17,17);painter.setPen(QColor('#f1f5f9'));painter.drawText(QRectF(-51,-21,102,42),Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,self.label[:32])
    def itemChange(self,change,value):
        if change==QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            for edge in self.edges:edge.adjust()
        return super().itemChange(change,value)
    def mousePressEvent(self,event):self.setCursor(Qt.CursorShape.ClosedHandCursor);super().mousePressEvent(event)
    def mouseReleaseEvent(self,event):self.setCursor(Qt.CursorShape.OpenHandCursor);super().mouseReleaseEvent(event)

class GraphEdge(QGraphicsLineItem):
    def __init__(self, source,target,label):
        super().__init__();self.source=source;self.target=target;self.label=label;source.edges.append(self);target.edges.append(self);self.setPen(QPen(QColor('#31516f'),1.4));self.setZValue(1);self.adjust()
    def adjust(self):
        a=self.source.pos();b=self.target.pos();self.setLine(a.x(),a.y(),b.x(),b.y())

class GraphPage(QWidget):
    def __init__(self, service):
        super().__init__();self.service=service;self.node_id=None;self.nodes=[];self.edges=[];layout=QVBoxLayout(self);header=QHBoxLayout();self.title=QLabel('Grafo');self.title.setObjectName('title');self.info=QLabel('Selecione um resultado e escolha “Mostrar no grafo”.');self.pause=QPushButton('Pausar movimento');self.pause.setCheckable(True);self.pause.toggled.connect(lambda paused:self.pause.setText('Retomar movimento' if paused else 'Pausar movimento'));header.addWidget(self.title);header.addWidget(self.info,1);header.addWidget(self.pause);layout.addLayout(header);self.scene=QGraphicsScene(-600,-400,1200,800);self.scene.setBackgroundBrush(QColor('#000000'));self.view=QGraphicsView(self.scene);self.view.setRenderHint(QPainter.RenderHint.Antialiasing);self.view.setBackgroundBrush(QColor('#000000'));self.view.setDragMode(QGraphicsView.DragMode.ScrollHandDrag);layout.addWidget(self.view,1);self.timer=QTimer(self);self.timer.timeout.connect(self.tick);self.timer.start(25)
    def show_node(self,node_id,label):
        self.node_id=node_id;edges=self.service.graph(node_id);self.scene.clear();self.nodes=[];self.edges=[];self._stars();self.info.setText(f'{label} · {len(edges)} relação(ões)'); center=self._node(label,QColor('#67e8f9'),True,QPointF(0,0))
        for i,edge in enumerate(edges):
            _,source_id,_,source_label,rel,target_id,_,target_label=edge;other_label=target_label if source_id==node_id else source_label;angle=2*math.pi*i/max(len(edges),1);other=self._node(other_label,QColor('#a78bfa'),False,QPointF(240*math.cos(angle),180*math.sin(angle)));self.edges.append(GraphEdge(center,other,rel));self.scene.addItem(self.edges[-1])
        self.view.centerOn(center)
    def _node(self,label,color,primary,pos):
        node=GraphNode(label,color,primary);node.setPos(pos);self.nodes.append(node);self.scene.addItem(node);return node
    def _stars(self):
        random.seed(17)
        for _ in range(115):
            x=random.randint(-590,590);y=random.randint(-390,390);size=random.choice([1,1,1,2]);star=self.scene.addEllipse(x,y,size,size,QPen(Qt.PenStyle.NoPen),QBrush(QColor(125,211,252,random.randint(25,120))));star.setZValue(-2)
    def tick(self):
        if self.pause.isChecked() or len(self.nodes)<2:return
        for node in self.nodes:
            force=QPointF()
            for other in self.nodes:
                if node is other:continue
                delta=node.pos()-other.pos();distance=max(30.0,math.hypot(delta.x(),delta.y()));strength=15000/(distance*distance*distance);force=QPointF(force.x()+delta.x()*strength,force.y()+delta.y()*strength)
            for edge in node.edges:
                other=edge.target if edge.source is node else edge.source;delta=other.pos()-node.pos();distance=max(1.0,math.hypot(delta.x(),delta.y()));strength=(distance-210)*0.0018/distance;force=QPointF(force.x()+delta.x()*strength,force.y()+delta.y()*strength)
            node.velocity=QPointF((node.velocity.x()+force.x())*.88,(node.velocity.y()+force.y())*.88)
        for node in self.nodes:
            if node.primary:continue
            position=node.pos();next_pos=QPointF(position.x()+node.velocity.x(),position.y()+node.velocity.y());next_pos.setX(max(-510,min(510,next_pos.x())));next_pos.setY(max(-320,min(320,next_pos.y())));node.setPos(next_pos)

class CollectionsPage(QWidget):
    def __init__(self,service):
        super().__init__();self.service=service;self.current=None;layout=QHBoxLayout(self);left=QVBoxLayout();create=QPushButton('+ Nova coleção');create.clicked.connect(self.create);left.addWidget(create);self.list=QListWidget();self.list.currentItemChanged.connect(self.select);left.addWidget(self.list,1);layout.addLayout(left,1);right=QVBoxLayout();self.heading=QLabel('Coleções');self.heading.setObjectName('title');right.addWidget(self.heading);self.items=QListWidget();right.addWidget(self.items,1);remove=QPushButton('Remover item selecionado');remove.clicked.connect(self.remove);right.addWidget(remove);layout.addLayout(right,2);self.refresh()
    def refresh(self):
        self.list.clear()
        for cid,name,desc,_ in self.service.collections(): item=QListWidgetItem(name);item.setData(Qt.ItemDataRole.UserRole,cid);item.setToolTip(desc or '');self.list.addItem(item)
    def create(self):
        name,ok=QInputDialog.getText(self,'Nova coleção','Nome:')
        if ok and name:
            desc,_=QInputDialog.getText(self,'Nova coleção','Descrição (opcional):');self.service.create_collection(name,desc);self.refresh()
    def select(self,item):
        self.items.clear();self.current=item.data(Qt.ItemDataRole.UserRole) if item else None;self.heading.setText(item.text() if item else 'Coleções')
        if self.current:
            for kind,obj,label in self.service.collection_items(self.current): entry=QListWidgetItem(f'{label} · {kind}');entry.setData(Qt.ItemDataRole.UserRole,(kind,obj));self.items.addItem(entry)
    def remove(self):
        entry=self.items.currentItem()
        if entry and self.current:
            kind,obj=entry.data(Qt.ItemDataRole.UserRole);self.service.remove_from_collection(self.current,kind,obj);self.select(self.list.currentItem())

class SettingsPage(QWidget):
    def __init__(self, settings, on_change):
        super().__init__();self.settings=settings;self.on_change=on_change;layout=QVBoxLayout(self);title=QLabel('Configuração de indexação');title.setObjectName('title');layout.addWidget(title);layout.addWidget(QLabel('Pastas monitorizadas e indexadas:'));self.paths=QListWidget();layout.addWidget(self.paths,1);buttons=QHBoxLayout();add=QPushButton('+ Adicionar pasta');add.clicked.connect(self.add);remove=QPushButton('Remover pasta');remove.clicked.connect(self.remove);save=QPushButton('Guardar configuração');save.clicked.connect(self.save);buttons.addWidget(add);buttons.addWidget(remove);buttons.addStretch();buttons.addWidget(save);layout.addLayout(buttons);layout.addWidget(QLabel('A configuração fica em config.toml. Os padrões de exclusão predefinidos incluem ficheiros temporários, .git, node_modules e cache.'));self.refresh()
    def refresh(self): self.paths.clear();self.paths.addItems(self.settings.directories)
    def add(self):
        path=QFileDialog.getExistingDirectory(self,'Adicionar pasta persistente')
        if path and path not in self.settings.directories:self.settings.directories.append(path);self.refresh()
    def remove(self):
        item=self.paths.currentItem()
        if item:self.settings.directories.remove(item.text());self.refresh()
    def save(self): self.settings.save();self.on_change();QMessageBox.information(self,'Configuração','config.toml guardado.')

class DetailPane(QWidget):
    def __init__(self, service):
        super().__init__(); self.service=service; self.file_id=None
        layout=QVBoxLayout(self); self.title=QLabel('Selecione um ficheiro'); self.title.setObjectName('title'); layout.addWidget(self.title)
        self.meta=QLabel(); self.meta.setWordWrap(True); layout.addWidget(self.meta)
        self.preview=QTextBrowser(); self.preview.setOpenExternalLinks(False); layout.addWidget(self.preview,1)
        self.tags=QLabel('Tags: —'); self.tags.setWordWrap(True); layout.addWidget(self.tags)
        self.relations=QLabel('Relações: —'); self.relations.setWordWrap(True); layout.addWidget(self.relations)
        buttons=QHBoxLayout(); self.open_btn=QPushButton('Abrir ficheiro'); self.open_btn.clicked.connect(self.open_file); self.dataset_btn=QPushButton('Tabela'); self.dataset_btn.clicked.connect(self.open_dataset);self.dataset_btn.hide();self.tag_btn=QPushButton('+ Tag'); self.tag_btn.clicked.connect(self.add_tag); self.relate_btn=QPushButton('+ Criar relação'); self.relate_btn.clicked.connect(self.create_relation); self.graph_btn=QPushButton('Mostrar no grafo');self.graph_btn.clicked.connect(self.show_graph);self.collection_btn=QPushButton('+ Coleção');self.collection_btn.clicked.connect(self.add_collection); [buttons.addWidget(x) for x in (self.open_btn,self.dataset_btn,self.tag_btn,self.relate_btn,self.graph_btn,self.collection_btn)]; layout.addLayout(buttons)
    def show_file(self, file_id):
        self.file_id=file_id; row=self.service.details(file_id)
        if not row: return
        cols=[d[0] for d in self.service.catalog.conn.description]; data=dict(zip(cols,row)); path=Path(data['path']); self.title.setText(data['filename']); self.meta.setText(f"{data['file_category'].upper()} · {data['size_bytes']:,} bytes\n{data['path']}")
        ext=path.suffix.lower()
        self.dataset_btn.setVisible(ext in {'.xlsx','.xls','.csv'})
        if ext in {'.png','.jpg','.jpeg','.gif','.bmp','.webp'}:
            image=QPixmap(str(path)); self.preview.setText(''); self.preview.document().addResource(2, self.preview.document().baseUrl(), image)
            self.preview.setHtml(f'<img src="file://{path}" style="max-width:100%;">')
        elif ext in {'.xlsx','.xls','.csv'}:
            info=self.service.dataset_preview(file_id); html='<h3>Dataset</h3>' + ''.join(f'<p><b>{s}</b> · {r:,} linhas × {c} colunas<br><small>{columns or ""}</small></p>' for s,r,c,columns in info); self.preview.setHtml(html or 'Sem dados estruturados.')
        else:
            text=data.get('text_content') or 'Preview de conteúdo não disponível para este formato.'; self.preview.setPlainText(text[:30000])
        tag_names=', '.join('#'+x[0] for x in self.service.tags(file_id)) or '—'; self.tags.setText('Tags: '+tag_names)
        rel=', '.join(f'→ {name} ({kind})' for _,name,kind in self.service.relations(file_id)) or '—'; self.relations.setText('Relações: '+rel)
    def open_file(self):
        if self.file_id:
            row=self.service.details(self.file_id); path=row[1]
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))
    def add_tag(self):
        if not self.file_id:return
        tag,ok=QInputDialog.getText(self,'Adicionar tag','Nome da tag:')
        if ok and tag: self.service.add_tag(self.file_id,tag); self.show_file(self.file_id)
    def create_relation(self):
        if not self.file_id: return
        kind, ok = QInputDialog.getItem(self, 'Criar relação', 'Relacionar com:', ['poc', 'contract', 'person', 'company', 'property', 'location', 'file', 'other'], 0, False)
        if not ok: return
        label, ok = QInputDialog.getText(self, 'Criar relação', f'Identificador ou nome de {kind}:')
        if ok and label:
            relation, ok = QInputDialog.getItem(self, 'Tipo de relação', 'Relação:', ['related_to', 'belongs_to', 'references', 'derived_from', 'supports', 'supersedes', 'same_subject'], 0, False)
            if ok: self.service.create_relation(self.file_id, kind, label, relation); self.show_file(self.file_id)
    def open_dataset(self):
        if not self.file_id:return
        row=self.service.details(self.file_id);window=QMainWindow(self);window.setWindowTitle('Preview de dados — '+row[3]);preview=DatasetPreview();preview.load(row[1]);window.setCentralWidget(preview);window.resize(950,600);window.show();self.dataset_window=window
    def show_graph(self):
        if self.file_id:self.window().show_graph(self.file_id)
    def add_collection(self):
        if not self.file_id:return
        items=self.service.collections()
        if not items: QMessageBox.information(self,'Coleções','Crie primeiro uma coleção na página Coleções.');return
        names=[row[1] for row in items];name,ok=QInputDialog.getItem(self,'Adicionar à coleção','Coleção:',names,0,False)
        if ok:self.service.add_to_collection(next(row[0] for row in items if row[1]==name),'file',self.file_id)

class MainWindow(QMainWindow):
    def __init__(self):
        from app.config import Settings
        super().__init__(); self.catalog=Catalog(); self.service=ExplorerService(self.catalog); self.settings=Settings.load(); self.setWindowTitle('Local Knowledge Explorer'); self.resize(1280,780); self._build(); self.search()
    def _build(self):
        bar=QToolBar('Principal'); self.addToolBar(bar); scan=QAction('Indexar pasta',self); scan.triggered.connect(self.choose_directory); bar.addAction(scan); saved=QAction('Indexar pastas configuradas',self);saved.triggered.connect(self.index_configured);bar.addAction(saved)
        root=QWidget(); self.setCentralWidget(root); outer=QHBoxLayout(root); outer.setContentsMargins(0,0,0,0)
        nav=QListWidget(); nav.setFixedWidth(175); nav.addItems(['Pesquisa','Ficheiros','Dados','Grafo','Coleções','Configuração']); nav.setCurrentRow(0); outer.addWidget(nav)
        self.pages=QStackedWidget(); outer.addWidget(self.pages,1); nav.currentRowChanged.connect(self.pages.setCurrentIndex)
        self.pages.addWidget(self._search_page()); self.pages.addWidget(self._files_page()); self.pages.addWidget(self._data_page()); self.graph_page=GraphPage(self.service);self.pages.addWidget(self.graph_page);self.collections_page=CollectionsPage(self.service);self.pages.addWidget(self.collections_page);self.pages.addWidget(SettingsPage(self.settings,self.config_changed))
        self.index_progress=QProgressBar();self.index_progress.setFixedWidth(240);self.index_progress.setTextVisible(True);self.index_progress.setFormat('Indexação: %p%');self.index_progress.hide();self.statusBar().addPermanentWidget(self.index_progress)
        self.statusBar().showMessage('Pronto — selecione “Indexar pasta” para começar.')
    def _search_page(self):
        page=QWidget(); layout=QVBoxLayout(page); controls=QHBoxLayout(); self.query=QLineEdit(); self.query.setPlaceholderText('Pesquisar ficheiros, conteúdo, pastas e colunas…'); self.query.returnPressed.connect(self.search); self.type_filter=QComboBox(); self.type_filter.addItem('Todos',None); self.type_filter.addItems(['document','spreadsheet','dataset','image']); btn=QPushButton('Pesquisar');btn.clicked.connect(self.search); controls.addWidget(self.query,1);controls.addWidget(self.type_filter);controls.addWidget(btn);layout.addLayout(controls)
        split=QSplitter(); self.results=QTableWidget(0,3);self.results.setHorizontalHeaderLabels(['Resultado','Tipo','Localização']);self.results.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows);self.results.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers);self.results.itemSelectionChanged.connect(self.select_result);split.addWidget(self.results);self.detail=DetailPane(self.service);split.addWidget(self.detail);split.setSizes([700,450]);layout.addWidget(split,1);return page
    def _files_page(self):
        p=QWidget();l=QVBoxLayout(p); label=QLabel('Ficheiros indexados aparecem nos resultados de pesquisa. Use uma pesquisa vazia para listar tudo.');l.addWidget(label);button=QPushButton('Ver todos os ficheiros');button.clicked.connect(lambda:(self.query.setText(''),self.pages.setCurrentIndex(0),self.search()));l.addWidget(button);l.addStretch();return p
    def _data_page(self): return self._placeholder('Dados','Pesquise por nome de coluna (por exemplo, “Concelho” ou “Área”) para encontrar ficheiros Excel e CSV. A preview mostra folhas, dimensões e esquema.')
    def _placeholder(self,title,text):
        p=QWidget();l=QVBoxLayout(p);h=QLabel(title);h.setObjectName('title');l.addWidget(h);l.addWidget(QLabel(text));l.addStretch();return p
    def search(self):
        rows=self.service.search(self.query.text(),self.type_filter.currentData()); self.results.setRowCount(len(rows))
        for i,(fid,name,path,ext,kind,size,score) in enumerate(rows):
            first=QTableWidgetItem(name);first.setData(Qt.ItemDataRole.UserRole,fid);self.results.setItem(i,0,first);self.results.setItem(i,1,QTableWidgetItem(kind));self.results.setItem(i,2,QTableWidgetItem(path))
        self.results.resizeColumnsToContents();self.statusBar().showMessage(f'{len(rows)} resultado(s)')
    def select_result(self):
        items=self.results.selectedItems()
        if items:self.detail.show_file(items[0].data(Qt.ItemDataRole.UserRole))
    def choose_directory(self):
        directory=QFileDialog.getExistingDirectory(self,'Selecionar pasta a indexar')
        if not directory:return
        self.start_index(directory, self.scan_done)
    def index_configured(self):
        valid=[path for path in self.settings.directories if Path(path).is_dir()]
        if not valid: QMessageBox.information(self,'Indexação','Adicione uma pasta em Configuração antes de indexar.');return
        self._configured_queue=valid;self._index_next_configured()
    def _index_next_configured(self):
        if not self._configured_queue:return
        directory=self._configured_queue.pop(0);self.start_index(directory, lambda a,b,c:(self.scan_done(a,b,c),self._index_next_configured()))
    def start_index(self,directory,on_finished):
        self.index_progress.setValue(0);self.index_progress.show();self.worker=ScanWorker(Indexer(self.catalog),directory);self.worker.progress.connect(self.update_index_progress);self.worker.finished.connect(on_finished);self.worker.start()
    def update_index_progress(self,current,total,name):
        self.index_progress.setRange(0,max(total,1));self.index_progress.setValue(current);self.statusBar().showMessage(f'A indexar {current}/{total}: {name}')
    def config_changed(self): self.statusBar().showMessage('Configuração guardada em config.toml.')
    def show_graph(self,file_id):
        row=self.service.details(file_id)
        if row:
            self.graph_page.show_node(file_id,row[3]);self.pages.setCurrentIndex(3)
    def scan_done(self,indexed,skipped,errors):
        self.index_progress.setValue(self.index_progress.maximum());self.index_progress.hide();self.statusBar().showMessage(f'Indexação concluída: {indexed} novos/alterados, {skipped} inalterados, {errors} erros.');self.search()
    def closeEvent(self,event): self.catalog.close();event.accept()
