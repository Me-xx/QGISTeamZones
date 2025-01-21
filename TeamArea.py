from qgis.core import QgsSimpleMarkerSymbolLayer,QgsSymbol,QgsLinePatternFillSymbolLayer,QgsSimpleLineSymbolLayer, QgsCoordinateTransformContext, QgsVectorFileWriter, QgsProject, QgsVectorLayer, QgsField, QgsFeature, QgsGeometry, QgsPointXY
from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtWidgets import QAction, QMessageBox, QInputDialog
import math
import os

class TeamZonesPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.canvas = iface.mapCanvas()
        self.colors = ["red","blue","green","yellow","grey","purple"]

    def initGui(self):
        self.action = QAction('TeamArea Creator', self.iface.mainWindow())
        self.action.setEnabled(True)
        self.action.triggered.connect(self.run)
        self.toolbar = self.iface.addToolBar("TeamArea Creator")
        self.toolbar.setObjectName("TeamArea Creator Toolbar")
        self.toolbar.addAction(self.action)
        self.menu = "TeamAreaCreator"
        self.iface.addPluginToMenu(self.menu, self.action)


    def unload(self):
        self.iface.removeToolBarIcon(self.action)

    def run(self):
        num_teams, ok = QInputDialog.getInt(self.iface.mainWindow(), 'Teamanzahl', 'Geben Sie die Anzahl der Teams ein:', 3, 1)
        if not ok:
            QMessageBox.warning(self.iface.mainWindow(), 'Abgebrochen', 'Benutzer hat die Eingabe abgebrochen.')
            return

        canvas = self.iface.mapCanvas()
        extent = canvas.extent()
        center_point = extent.center()

        self.create_team_layers(num_teams, center_point)

    def create_team_layers(self, num_teams, center_point):
        project = QgsProject.instance()
        
        angle_step = 360 / num_teams
        radius = 0.01  # Beispielradius, kann angepasst werden
        # Aktueller Projektpfad
        project_path = QgsProject.instance().homePath()
        vorgaben_gpkg_path = os.path.join(project_path, "Vorgaben.gpkg")
        sammlung_gpkg_path = os.path.join(project_path, "Sammlung.gpkg")

        for team_id in range(num_teams):
            angle = angle_step * team_id
            dx = radius * math.cos(math.radians(angle))
            dy = radius * math.sin(math.radians(angle))
            team_point = QgsPointXY(center_point.x() + dx, center_point.y() + dy)
            self.create_polygon_layer(vorgaben_gpkg_path, team_id + 1, team_point)
            self.create_point_layer(sammlung_gpkg_path, team_id + 1, team_point)

    def create_point_layer(self, gpkg_path, team_id, center_point):
        layer_name = f'Sammlung_Team_{team_id}'
        layer = QgsVectorLayer(f"Point?crs=EPSG:4326&index=yes", layer_name, "memory")
        options = QgsVectorFileWriter.SaveVectorOptions()
        options.driverName = "GPKG"
        options.layerName = layer_name
        options.createEmpty = True
        options.actionOnExistingFile=1 # CanAddNewLayer

        # Speichere das leere Layer in der GeoPackage-Datei
        error = QgsVectorFileWriter.writeAsVectorFormatV3(
            layer=layer,
            fileName=gpkg_path,
            transformContext=QgsProject.instance().transformContext(),
            options=options
        )
        print("Done",gpkg_path, layer_name)
        if error[0] != QgsVectorFileWriter.NoError:
            print("Fehler beim Erstellen des Layers:", error)
        else:
            # Lade das neu erstellte Layer aus der GeoPackage-Datei
            layer = QgsVectorLayer(f"{gpkg_path}|layername={layer_name}", layer_name, "ogr")

            prov = layer.dataProvider()
            # Attribute definieren
            prov.addAttributes([QgsField('Count', QVariant.Int)])
            layer.updateFields()

            symbol = QgsSymbol.defaultSymbol(layer.geometryType())
            symbol.setColor(self.get_color(team_id))

            layer.renderer().setSymbol(symbol)
            feature = QgsFeature()
            feature.setGeometry(QgsGeometry.fromPointXY(center_point))
            feature.setAttributes([team_id])
            prov.addFeature(feature)
            layer.updateExtents()

            # Layer zum Projekt hinzufügen
            QgsProject.instance().addMapLayer(layer)
    def get_color(self, this_id):
        return QColor(self.colors[this_id%len(self.colors)])

    def create_polygon_layer(self, gpkg_path, team_id, center_point):
        layer_name = f'Gebiet_Team_{team_id}'

        layer = QgsVectorLayer(f"Polygon?crs=EPSG:4326&index=yes", layer_name, "memory")
        options = QgsVectorFileWriter.SaveVectorOptions()
        options.driverName = "GPKG"
        options.layerName = layer_name
        options.createEmpty = True
        options.actionOnExistingFile=1 # CanAddNewLayer
        print("Done",gpkg_path, layer_name)
        # Speichere das leere Layer in der GeoPackage-Datei
        error = QgsVectorFileWriter.writeAsVectorFormatV3(
            layer=layer,
            fileName=gpkg_path,
            transformContext=QgsProject.instance().transformContext(),
            options=options
        )

        if error[0] != QgsVectorFileWriter.NoError:
            print("Fehler beim Erstellen des Layers:", error)
        else:
            # Lade das neu erstellte Layer aus der GeoPackage-Datei
            layer = QgsVectorLayer(f"{gpkg_path}|layername={layer_name}", layer_name, "ogr")

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
            prov.addAttributes([QgsField('TeamContact', QVariant.String)])
            layer.updateFields()

            # Polygon erstellen
            points = [
                QgsPointXY(center_point.x() - 2, center_point.y() - 2),
                QgsPointXY(center_point.x() + 2, center_point.y() - 2),
                QgsPointXY(center_point.x() + 2, center_point.y() + 2),
                QgsPointXY(center_point.x() - 2, center_point.y() + 2),
                QgsPointXY(center_point.x() - 2, center_point.y() - 2)
            ]
            feature = QgsFeature()
            feature.setGeometry(QgsGeometry.fromPolygonXY([points]))
            feature.setAttributes([team_id])
            prov.addFeature(feature)
            layer.updateExtents()

            # Layer zum Projekt hinzufügen
            QgsProject.instance().addMapLayer(layer)




