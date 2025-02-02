from qgis.core import QgsSimpleMarkerSymbolLayer,QgsSymbol,QgsLinePatternFillSymbolLayer
from qgis.core import QgsSimpleLineSymbolLayer, QgsCoordinateTransformContext, QgsVectorFileWriter, QgsProject
from qgis.core import  QgsVectorLayer, QgsField, QgsFeature, QgsGeometry, QgsPointXY, QgsApplication
from qgis.PyQt.QtCore import QVariant, QMetaType
from qgis.PyQt import uic
from qgis.PyQt.QtCore import QCoreApplication, QTranslator, QAbstractItemModel
from qgis.PyQt.QtGui import QColor,QStandardItemModel, QStandardItem
from qgis.PyQt.QtWidgets import QAction, QMessageBox, QInputDialog, QComboBox, QFileDialog, QHeaderView
from qgis.PyQt.QtWidgets import QDialog, QVBoxLayout, QLineEdit, QSpinBox, QDialogButtonBox
#muss in osgeo4w shell mit python -m pip install installiert werden
import re
import logging
import polars as pl
import xlsxwriter
import math
import os

FORM_CLASS, _ = uic.loadUiType(os.path.join(os.path.dirname(__file__), r'gui\AreaCreator.ui'))

class TeamZonesPlugin(QDialog, FORM_CLASS):
    def __init__(self, iface):
        QDialog.__init__(self)
        self.setupUi(self)
        self.iface = iface
        self.canvas = iface.mapCanvas()
        self.colors = ["red","blue","green","yellow","grey","purple"]
        self.sampattern = re.compile(r'Sammlung_Team_[0-9]+')

        logging.basicConfig(filename=r'C:\temp\export_layers_to_excel.log', level=logging.DEBUG,
                            format='%(asctime)s:%(levelname)s:%(message)s')

        #GUI PreFill
        self.qt_FTyp.addItems(["String", "Integer", "Double"])
        self.qt_xlFile.setFilter("*.xlsx")
        #TODO get and store XLPAth to config

        # Model for QColumnView
        self.model = QStandardItemModel()
        self.model.setColumnCount(2)
        self.model.setHorizontalHeaderLabels([self.tr("Field Name"), self.tr("Field Type")])
        self.qtCVfields.setModel(self.model)

        # Set the header to display both columns
        #self.qtCVfields.header().setStretchLastSection(False)
        #self.qtCVfields.header().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.model.appendRow([QStandardItem("Count"), QStandardItem("Integer")])

        # Connect signals
        self.qt_pb_Add.clicked.connect(self.add_field)
        self.qt_pb_Remove.clicked.connect(self.remove_field)
        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)

    def initGui(self):
        self.action = QAction('TeamArea Creator', self.iface.mainWindow())
        self.action.setEnabled(True)
        self.action.triggered.connect(self.show_dialog)
        self.toolbar = self.iface.addToolBar("TeamArea Creator")
        self.toolbar.setObjectName("TeamArea Creator Toolbar")
        self.mainaction = QAction(self.tr('Build Team Layers'), self.iface.mainWindow())
        self.mainaction.setEnabled(True)
        self.mainaction.triggered.connect(self.show_dialog)
        self.toolbar.addAction(self.mainaction)
        self.menu = self.tr("TeamAreaCreator")
        self.iface.addPluginToMenu(self.menu, self.mainaction)
        self.expaction = QAction(self.tr('Evaluate Team Layers'), self.iface.mainWindow())
        self.expaction.setEnabled(True)
        self.expaction.triggered.connect(self.export_layers_to_excel)
        self.iface.addPluginToMenu(self.menu, self.expaction)


    def unload(self):
        #self.iface.removeToolBar(self.toolbar)
        self.iface.removePluginMenu(self.menu, self.mainaction)
        self.iface.removePluginMenu(self.menu, self.expaction)
        del self.toolbar

    def convert_qvariant(self, qvalue):
        """Konvertiert QVariant in Standard-Python-Datentypen mithilfe von QMetaType."""
        if isinstance(qvalue, QVariant):
            #logging.info('Value:'+str(qvalue))
            #logging.info('ValueDir:'+str(dir(qvalue)))
            #logging.info('SubValue:'+str(qvalue.value()))
            meta_type = qvalue.type()
            if qvalue.isNull():
                return 0
            elif meta_type == QMetaType.Int:
                return int(qvalue.value())
            elif meta_type == QMetaType.Double:
                return float(qvalue.value())
            elif meta_type == QMetaType.Bool:
                return bool(qvalue.value())
            elif meta_type == QMetaType.QString:
                return str(qvalue.value())
            elif meta_type == QMetaType.QDate:
                return str(qvalue.value()) #TODO qvalue.toDate().toString("yyyy-MM-dd")
            elif meta_type == QMetaType.QDateTime:
                return str(qvalue.value()) #TODO qvalue.toDateTime().toString("yyyy-MM-dd HH:mm:ss")
            else:
                return str(qvalue.value())
        else:
            return qvalue

    def show_dialog(self):
        self.show()

    def accept(self):
        num_teams = int(self.qt_NTeams.value())
        self.radius = float(self.qt_radius.text())
        if not (self.radius > 0.00001):
            self.radius = 0.01
        super().accept()
        self.run(num_teams)

    def add_field(self):
        field_name = self.qt_FName.text()
        field_type = self.qt_FTyp.currentText()
        if field_name and field_type:
            item_name = QStandardItem(field_name)
            item_type = QStandardItem(field_type)
            self.model.appendRow([item_name, item_type])
            self.qt_FName.clear()

    def remove_field(self):
        selected_index = self.qtCVfields.selectedIndexes()
        if selected_index:
            self.model.removeRow(selected_index[0].row())

    def read_fields(self):
        fields = []
        for row in range(self.model.rowCount()):
            field_name = self.model.item(row, 0).text()
            field_type = self.model.item(row, 1).text()
            fields.append((field_name, field_type))
        return fields

    def tr(self, message):
        return QCoreApplication.translate('TeamZonesPlugin', message)

    def run(self, num_teams=None):
        #num_teams, ok = QInputDialog.getInt(self.iface.mainWindow(), 'Teamanzahl', 'Geben Sie die Anzahl der Teams ein:', 3, 1)
        if num_teams is None:
            QMessageBox.warning(self.iface.mainWindow(), self.tr('Fehler'), self.tr('Anzahl')+self.tr('der Teams wurde nicht festgelegt.'))
            return
        logging.info(f"Es wurden {num_teams} Teams definiert.")
        canvas = self.iface.mapCanvas()
        extent = canvas.extent()
        center_point = extent.center()
        self.create_team_layers(num_teams, center_point)

    def getSamLayerName(self, team_id):
        return self.tr("Sammlung") + "_Team_" + str(team_id)

    def getAreaLayerName(self, team_id):
        return self.tr("Gebiet")+"_Team_" + str(team_id)

    def getTraceLayerName(self, team_id):
        return self.tr("Trace") + "_Team_" + str(team_id)

    def create_team_layers(self, num_teams, center_point):
        project = QgsProject.instance()

        angle_step = 360 / num_teams
        # Aktueller Projektpfad
        project_path = QgsProject.instance().homePath()
        vorgaben_gpkg_path = os.path.join(project_path, "Vorgaben.gpkg")
        sammlung_gpkg_path = os.path.join(project_path, "Sammlung.gpkg")

        logging.info(f"Es wurden {num_teams} Teams definiert. Und in {project_path} angelegt.")

        for team_id in range(num_teams):
            team_num = team_id+1
            angle = angle_step * team_id
            dx = self.radius * math.cos(math.radians(angle))
            dy = self.radius * math.sin(math.radians(angle))
            team_point = QgsPointXY(center_point.x() + dx, center_point.y() + dy)
            teamLayerDoesNotExist = True
            for layer in project.mapLayers().values():
                if layer.name() == self.getSamLayerName(team_num):
                    logging.info(layer.name() + "existiert.")
                    teamLayerDoesNotExist = False
            if teamLayerDoesNotExist:
                logging.info("Handle " + self.getAreaLayerName(team_num))
                self.create_polygon_layer(vorgaben_gpkg_path, team_num, team_point,  self.getAreaLayerName(team_num))
                self.create_point_layer(sammlung_gpkg_path, team_num, self.read_fields(), self.getSamLayerName(team_num))
                self.create_point_layer(sammlung_gpkg_path, team_num, [("Speed","Double")], self.getTraceLayerName(team_num))

    def determine_schema(self, layer_fields):
        """Bestimmt das Schema für den DataFrame basierend auf den Feldtypen."""
        schema = {}
        for field in layer_fields:
            if field.type() == QVariant.Int:
                schema[field.name()] = pl.Int64
            elif field.type() == QVariant.Double:
                schema[field.name()] = pl.Float64
            elif field.type() == QVariant.Bool:
                schema[field.name()] = pl.Boolean
            elif field.type() == QVariant.String:
                schema[field.name()] = pl.Utf8
            elif field.type() == QVariant.Date or field.type() == QVariant.DateTime:
                schema[field.name()] = pl.Utf8
            else:
                schema[field.name()] = pl.Utf8
        return schema

    def select_excel_file(self):
        options = QFileDialog.Options()
        file_path, _ = QFileDialog.getSaveFileName(self, self.tr("Save Excel File"), self.qt_xlFile.filePath(), self.tr("Excel Files (*.xlsx)"), options=options)
        if file_path:
            self.qt_xlFile.setFilePath(file_path)

    def export_layers_to_excel(self):
        self.select_excel_file()

        #excel_path = "C:/temp/Team_Sammlung_Data.xlsx"
        excel_path =self.qt_xlFile.filePath()
        try:
            # Iterate over all layers in the project
            project = QgsProject.instance()
            # Regular expression to match layer names

            # Dataframe to hold all data
            # Dataframe to hold all data

            # Dataframe to hold all data
            all_data = []

            # Iterate over all layers in the project
            for layer in project.mapLayers().values():
                if self.sampattern.match(layer.name()):
                    logging.info('Parsing Layer' + str(layer.name()))
                    # Prepare a list to hold feature data
                    features_data = []
                    for feature in layer.getFeatures():
                        feature_data = [self.convert_qvariant(value) for value in feature.attributes()]  # Convert attributes
                        feature_data.append(layer.name())  # Append the layer name
                        features_data.append(feature_data)
                    #logging.info('Features' + str(features_data))

                    # Create a dataframe for the current layer
                    layer_fields = [field for field in layer.fields()] # QgsProject.instance().mapLayers().values().fields()
                    layer_fields.append(QgsField("Layer Name", QMetaType.QString))
                    schema = self.determine_schema(layer_fields)
                    #logging.info('Schema' + str(schema))
                    if features_data:
                        layer_df = pl.DataFrame(data = features_data, schema=schema, orient="row", strict=False) #
                       # layer_df.columns = layer_fields

                        # Append the dataframe to all_data
                        all_data.append(layer_df)

            logging.info('Data' + str(all_data))

            if all_data:
                # Concatenate all dataframes
                final_df = pl.concat(all_data)
                #logging.info('FinalDF' + str(final_df))

                # Save the dataframe to an Excel file
                with xlsxwriter.Workbook(excel_path) as workbook:
                    worksheet = workbook.add_worksheet("Layer Data")
                    for i, col in enumerate(final_df.columns):
                        worksheet.write(0, i, col)
                    for row_idx, row in enumerate(final_df.rows()):
                        for col_idx, cell in enumerate(row):
                            worksheet.write(row_idx + 1, col_idx, cell)
                            #logging.info(f'Writing to cell ({row_idx + 1}, {col_idx}): {cell}')

                logging.info(f'Workbook saved to {excel_path}.')

                # Open the Excel file
                os.system(f'start excel.exe "{excel_path}"')
                logging.info('Workbook opened successfully.')
            else:
                logging.info('No Data do be exported.')

        except Exception as e:
            logging.error(f"An error occurred: {e}")

    def createAndLoadLayer(self, gpkg_path,layer_name,geometry):
        layer = QgsVectorLayer(f"{geometry}?crs=EPSG:4326&index=yes", layer_name, "memory")
        options = QgsVectorFileWriter.SaveVectorOptions()
        options.driverName = "GPKG"
        options.layerName = layer_name
        options.createEmpty = True
        if os.path.exists(gpkg_path):
            options.actionOnExistingFile=1 # CanAddNewLayer, EditionCapabilities
        else:
            options.actionOnExistingFile=0 # CreateOrOverwriteFile

        # Speichere das leere Layer in der GeoPackage-Datei
        error = QgsVectorFileWriter.writeAsVectorFormatV3(
            layer=layer,
            fileName=gpkg_path,
            transformContext=QgsProject.instance().transformContext(),
            options=options
        )
        logging.info(f"Polygon {layer_name} in {gpkg_path} für {layer.dataUrl()} und {layer.name()}")
        # Speichere das leere Layer in der GeoPackage-Datei
        if not os.path.exists(os.path.dirname(gpkg_path)):
            os.makedirs(os.path.dirname(gpkg_path))

        if error[0] != QgsVectorFileWriter.NoError:
            logging.error(f"Fehler beim Erstellen des Layers:{error}")
            return None
        else:
            # Lade das neu erstellte Layer aus der GeoPackage-Datei
            layer = QgsVectorLayer(f"{gpkg_path}|layername={layer_name}", layer_name, "ogr")
            logging.info(f"Loaded {layer.dataUrl()} und {layer.name()}")
            return layer
    def create_point_layer(self, gpkg_path, team_id, attributeList, layer_name):
            self.createAndLoadLayer(gpkg_path,layer_name,"Point")
            # Lade das neu erstellte Layer aus der GeoPackage-Datei
            layer = QgsVectorLayer(f"{gpkg_path}|layername={layer_name}", layer_name, "ogr")

            prov = layer.dataProvider()
            # Attribute definieren
            logging.info(f"Attribute:{attributeList}")
            for thisatt, at_type in attributeList:
                if at_type == "Integer":
                    prov.addAttributes([QgsField(thisatt, QMetaType.Int)])
                elif at_type == "String":
                    prov.addAttributes([QgsField(thisatt, QMetaType.QString)])
                elif at_type == "Double":
                    prov.addAttributes([QgsField(thisatt, QMetaType.Double)])
                layer.updateFields()

            symbol = QgsSymbol.defaultSymbol(layer.geometryType())
            symbol.setColor(self.get_color(team_id))

            layer.renderer().setSymbol(symbol)

            layer.updateExtents()

            # Layer zum Projekt hinzufügen
            QgsProject.instance().addMapLayer(layer)
    def get_color(self, this_id):
        return QColor(self.colors[this_id%len(self.colors)])

    def create_polygon_layer(self, gpkg_path, team_id, center_point, layer_name):
        layer = self.createAndLoadLayer(gpkg_path, layer_name, "Polygon")
        if None:
            logging.error(f"Error creating Layer{layer_name}")
        else:

            # Ändere die Füllung des Polygons auf ein 45° Linienmuster
            line_pattern_fill = QgsLinePatternFillSymbolLayer()
            line_pattern_fill.setLineAngle(45)
            line_pattern_fill.setDistance(2)
            line_pattern_fill.setColor(self.get_color(team_id))
            simple_fill = QgsSimpleLineSymbolLayer(self.get_color(team_id))

            # Kombiniere beide Symbol-Layer
            symbol = QgsSymbol.defaultSymbol(layer.geometryType())
            for i in range(symbol.symbolLayerCount()):
                symbol.deleteSymbolLayer(0)
            symbol.appendSymbolLayer(simple_fill)
            symbol.appendSymbolLayer(line_pattern_fill)

            # Setze das kombinierte Symbol für das Polygonlayer
            layer.renderer().setSymbol(symbol)


            prov = layer.dataProvider()

            # Attribute definieren
            prov.addAttributes([QgsField('TeamContact', QMetaType.QString)]) # QVariant, 'String')])
            layer.updateFields()

            # Polygon erstellen
            logging.info(f"Team{team_id} starts at {center_point.x()} / {center_point.y()}")
            areaSize = self.radius / 2
            points = [
                QgsPointXY(center_point.x() - areaSize, center_point.y() - areaSize),
                QgsPointXY(center_point.x() + areaSize, center_point.y() - areaSize),
                QgsPointXY(center_point.x() + areaSize, center_point.y() + areaSize),
                QgsPointXY(center_point.x() - areaSize, center_point.y() + areaSize),
                QgsPointXY(center_point.x() - areaSize, center_point.y() - areaSize)
            ]
            feature = QgsFeature()
            feature.setGeometry(QgsGeometry.fromPolygonXY([points]))
            feature.setAttributes([team_id])
            prov.addFeature(feature)
            layer.updateExtents()

            # Layer zum Projekt hinzufügen
            QgsProject.instance().addMapLayer(layer)




