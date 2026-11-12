# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'main_window.ui'
##
## Created by: Qt User Interface Compiler version 6.11.2
##
## WARNING! All changes made in this file will be lost when recompiling UI file!
################################################################################

from PySide6.QtCore import (QCoreApplication, QDate, QDateTime, QLocale,
    QMetaObject, QObject, QPoint, QRect,
    QSize, QTime, QUrl, Qt)
from PySide6.QtGui import (QAction, QBrush, QColor, QConicalGradient,
    QCursor, QFont, QFontDatabase, QGradient,
    QIcon, QImage, QKeySequence, QLinearGradient,
    QPainter, QPalette, QPixmap, QRadialGradient,
    QTransform)
from PySide6.QtWidgets import (QApplication, QFrame, QHBoxLayout, QHeaderView,
    QLabel, QMainWindow, QMenu, QMenuBar,
    QSizePolicy, QSlider, QSpacerItem, QSplitter,
    QStackedWidget, QStatusBar, QTableView, QToolButton,
    QVBoxLayout, QWidget)

from ui_helpers.sidebars.catalog_sidebar import CatalogSidebar
from ui_helpers.widgets.filter_bar import FilterBar
from ui_helpers.widgets.media_grid_view import MediaGridView
from ui_helpers.widgets.organize_bar import OrganizeBar
from ui_helpers.widgets.single_media_view import SingleMediaView
from ui_helpers.widgets.sort_control import SortControl
from ui_helpers.widgets.view_buttons import ViewButtons

import resources.recursos_rc  # noqa: F401


class Ui_MainWindow(object):
    def setupUi(self, MainWindow):
        if not MainWindow.objectName():
            MainWindow.setObjectName(u"MainWindow")
        MainWindow.resize(1200, 750)
        self.action_load_folder = QAction(MainWindow)
        self.action_load_folder.setObjectName(u"action_load_folder")
        self.action_exit = QAction(MainWindow)
        self.action_exit.setObjectName(u"action_exit")
        self.action_about = QAction(MainWindow)
        self.action_about.setObjectName(u"action_about")
        self.action_new_catalog = QAction(MainWindow)
        self.action_new_catalog.setObjectName(u"action_new_catalog")
        self.action_save = QAction(MainWindow)
        self.action_save.setObjectName(u"action_save")
        self.action_save_as = QAction(MainWindow)
        self.action_save_as.setObjectName(u"action_save_as")
        self.action_convert_format = QAction(MainWindow)
        self.action_convert_format.setObjectName(u"action_convert_format")
        self.action_add_files = QAction(MainWindow)
        self.action_add_files.setObjectName(u"action_add_files")
        self.action_add_folder = QAction(MainWindow)
        self.action_add_folder.setObjectName(u"action_add_folder")
        self.action_open_catalog = QAction(MainWindow)
        self.action_open_catalog.setObjectName(u"action_open_catalog")
        self.widget_central_main = QWidget(MainWindow)
        self.widget_central_main.setObjectName(u"widget_central_main")
        self.layout_central_main = QVBoxLayout(self.widget_central_main)
        self.layout_central_main.setSpacing(0)
        self.layout_central_main.setObjectName(u"layout_central_main")
        self.layout_central_main.setContentsMargins(0, 0, 0, 0)
        self.layout_content = QHBoxLayout()
        self.layout_content.setSpacing(0)
        self.layout_content.setObjectName(u"layout_content")
        self.layout_content.setContentsMargins(0, 0, 0, 0)
        self.frame_toolbar = QFrame(self.widget_central_main)
        self.frame_toolbar.setObjectName(u"frame_toolbar")
        self.frame_toolbar.setMaximumSize(QSize(60, 16777215))
        self.frame_toolbar.setFrameShape(QFrame.NoFrame)
        self.layout_toolbar = QVBoxLayout(self.frame_toolbar)
        self.layout_toolbar.setSpacing(4)
        self.layout_toolbar.setObjectName(u"layout_toolbar")
        self.layout_toolbar.setContentsMargins(0, 0, 0, 0)
        self.btn_catalog = QToolButton(self.frame_toolbar)
        self.btn_catalog.setObjectName(u"btn_catalog")
        self.btn_catalog.setMinimumSize(QSize(40, 40))
        self.btn_catalog.setIconSize(QSize(24, 24))
        self.btn_catalog.setAutoRaise(True)

        self.layout_toolbar.addWidget(self.btn_catalog)

        self.btn_image = QToolButton(self.frame_toolbar)
        self.btn_image.setObjectName(u"btn_image")
        self.btn_image.setMinimumSize(QSize(40, 40))
        self.btn_image.setIconSize(QSize(24, 24))
        self.btn_image.setAutoRaise(True)

        self.layout_toolbar.addWidget(self.btn_image)

        self.btn_video = QToolButton(self.frame_toolbar)
        self.btn_video.setObjectName(u"btn_video")
        self.btn_video.setMinimumSize(QSize(40, 40))
        self.btn_video.setIconSize(QSize(24, 24))
        self.btn_video.setAutoRaise(True)

        self.layout_toolbar.addWidget(self.btn_video)

        self.btn_audio = QToolButton(self.frame_toolbar)
        self.btn_audio.setObjectName(u"btn_audio")
        self.btn_audio.setMinimumSize(QSize(40, 40))
        self.btn_audio.setIconSize(QSize(24, 24))
        self.btn_audio.setAutoRaise(True)

        self.layout_toolbar.addWidget(self.btn_audio)

        self.spacer_toolbar_vertical = QSpacerItem(20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)

        self.layout_toolbar.addItem(self.spacer_toolbar_vertical)

        self.btn_settings = QToolButton(self.frame_toolbar)
        self.btn_settings.setObjectName(u"btn_settings")
        self.btn_settings.setMinimumSize(QSize(40, 40))
        self.btn_settings.setIconSize(QSize(24, 24))
        self.btn_settings.setAutoRaise(True)

        self.layout_toolbar.addWidget(self.btn_settings)


        self.layout_content.addWidget(self.frame_toolbar)

        self.splitter_main = QSplitter(self.widget_central_main)
        self.splitter_main.setObjectName(u"splitter_main")
        self.splitter_main.setOrientation(Qt.Horizontal)
        self.splitter_main.setOpaqueResize(True)
        self.splitter_main.setChildrenCollapsible(False)
        self.widget_sidebar_catalog = QWidget(self.splitter_main)
        self.widget_sidebar_catalog.setObjectName(u"widget_sidebar_catalog")
        self.widget_sidebar_catalog.setMinimumSize(QSize(180, 0))
        self.widget_sidebar_catalog.setMaximumSize(QSize(500, 16777215))
        self.layout_sidebar_catalog = QVBoxLayout(self.widget_sidebar_catalog)
        self.layout_sidebar_catalog.setSpacing(6)
        self.layout_sidebar_catalog.setObjectName(u"layout_sidebar_catalog")
        self.layout_sidebar_catalog.setContentsMargins(0, 0, 0, 0)
        self.stacked_widget_sidebar_catalog = QStackedWidget(self.widget_sidebar_catalog)
        self.stacked_widget_sidebar_catalog.setObjectName(u"stacked_widget_sidebar_catalog")
        self.page_catalog_default = QWidget()
        self.page_catalog_default.setObjectName(u"page_catalog_default")
        self.layout_page_catalog_default = QVBoxLayout(self.page_catalog_default)
        self.layout_page_catalog_default.setObjectName(u"layout_page_catalog_default")
        self.layout_page_catalog_default.setContentsMargins(0, 0, 0, 0)
        self.widget_catalog_sidebar = CatalogSidebar(self.page_catalog_default)
        self.widget_catalog_sidebar.setObjectName(u"widget_catalog_sidebar")

        self.layout_page_catalog_default.addWidget(self.widget_catalog_sidebar)

        self.stacked_widget_sidebar_catalog.addWidget(self.page_catalog_default)

        self.layout_sidebar_catalog.addWidget(self.stacked_widget_sidebar_catalog)

        self.splitter_main.addWidget(self.widget_sidebar_catalog)
        self.widget_central_area = QWidget(self.splitter_main)
        self.widget_central_area.setObjectName(u"widget_central_area")
        self.layout_central_area = QVBoxLayout(self.widget_central_area)
        self.layout_central_area.setSpacing(0)
        self.layout_central_area.setObjectName(u"layout_central_area")
        self.layout_central_area.setContentsMargins(0, 0, 0, 0)
        self.frame_main_top = QFrame(self.widget_central_area)
        self.frame_main_top.setObjectName(u"frame_main_top")
        self.frame_main_top.setFrameShape(QFrame.StyledPanel)
        self.layout_main_top = QHBoxLayout(self.frame_main_top)
        self.layout_main_top.setSpacing(0)
        self.layout_main_top.setObjectName(u"layout_main_top")
        self.layout_main_top.setContentsMargins(0, 0, 0, 0)
        self.widget_filter_bar = FilterBar(self.frame_main_top)
        self.widget_filter_bar.setObjectName(u"widget_filter_bar")

        self.layout_main_top.addWidget(self.widget_filter_bar)


        self.layout_central_area.addWidget(self.frame_main_top)

        self.layout_main_center = QVBoxLayout()
        self.layout_main_center.setObjectName(u"layout_main_center")
        self.layout_main_center.setContentsMargins(0, 0, 0, 0)
        self.stacked_widget_main = QStackedWidget(self.widget_central_area)
        self.stacked_widget_main.setObjectName(u"stacked_widget_main")
        self.page_list = QWidget()
        self.page_list.setObjectName(u"page_list")
        self.layout_page_list = QVBoxLayout(self.page_list)
        self.layout_page_list.setObjectName(u"layout_page_list")
        self.layout_page_list.setContentsMargins(0, 0, 0, 0)
        self.table_view_list = QTableView(self.page_list)
        self.table_view_list.setObjectName(u"table_view_list")

        self.layout_page_list.addWidget(self.table_view_list)

        self.stacked_widget_main.addWidget(self.page_list)
        self.page_grid = QWidget()
        self.page_grid.setObjectName(u"page_grid")
        self.layout_page_grid = QVBoxLayout(self.page_grid)
        self.layout_page_grid.setObjectName(u"layout_page_grid")
        self.layout_page_grid.setContentsMargins(0, 0, 0, 0)
        self.list_view_grid = MediaGridView(self.page_grid)
        self.list_view_grid.setObjectName(u"list_view_grid")

        self.layout_page_grid.addWidget(self.list_view_grid)

        self.stacked_widget_main.addWidget(self.page_grid)
        self.page_single = QWidget()
        self.page_single.setObjectName(u"page_single")
        self.layout_page_single = QVBoxLayout(self.page_single)
        self.layout_page_single.setObjectName(u"layout_page_single")
        self.layout_page_single.setContentsMargins(0, 0, 0, 0)
        self.widget_single_view = SingleMediaView(self.page_single)
        self.widget_single_view.setObjectName(u"widget_single_view")

        self.layout_page_single.addWidget(self.widget_single_view)

        self.stacked_widget_main.addWidget(self.page_single)

        self.layout_main_center.addWidget(self.stacked_widget_main)


        self.layout_central_area.addLayout(self.layout_main_center)

        self.frame_main_bottom = QFrame(self.widget_central_area)
        self.frame_main_bottom.setObjectName(u"frame_main_bottom")
        self.frame_main_bottom.setMinimumSize(QSize(0, 35))
        self.frame_main_bottom.setFrameShape(QFrame.StyledPanel)
        self.layout_main_bottom = QHBoxLayout(self.frame_main_bottom)
        self.layout_main_bottom.setObjectName(u"layout_main_bottom")
        self.layout_main_bottom.setContentsMargins(6, 2, 6, 2)
        self.widget_bottom_left = QWidget(self.frame_main_bottom)
        self.widget_bottom_left.setObjectName(u"widget_bottom_left")
        self.layout_bottom_left = QHBoxLayout(self.widget_bottom_left)
        self.layout_bottom_left.setObjectName(u"layout_bottom_left")
        self.layout_bottom_left.setContentsMargins(0, 0, 0, 0)
        self.widget_view_buttons = ViewButtons(self.widget_bottom_left)
        self.widget_view_buttons.setObjectName(u"widget_view_buttons")

        self.layout_bottom_left.addWidget(self.widget_view_buttons)

        self.line_bottom_views = QFrame(self.widget_bottom_left)
        self.line_bottom_views.setObjectName(u"line_bottom_views")
        self.line_bottom_views.setMaximumSize(QSize(1, 18))
        self.line_bottom_views.setFrameShape(QFrame.Shape.VLine)
        self.line_bottom_views.setFrameShadow(QFrame.Shadow.Sunken)

        self.layout_bottom_left.addWidget(self.line_bottom_views)

        self.widget_sort_control = SortControl(self.widget_bottom_left)
        self.widget_sort_control.setObjectName(u"widget_sort_control")

        self.layout_bottom_left.addWidget(self.widget_sort_control)

        self.spacer_bottom_left = QSpacerItem(0, 0, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.layout_bottom_left.addItem(self.spacer_bottom_left)


        self.layout_main_bottom.addWidget(self.widget_bottom_left)

        self.widget_organize_bar = OrganizeBar(self.frame_main_bottom)
        self.widget_organize_bar.setObjectName(u"widget_organize_bar")

        self.layout_main_bottom.addWidget(self.widget_organize_bar)

        self.widget_bottom_right = QWidget(self.frame_main_bottom)
        self.widget_bottom_right.setObjectName(u"widget_bottom_right")
        self.layout_bottom_right = QHBoxLayout(self.widget_bottom_right)
        self.layout_bottom_right.setObjectName(u"layout_bottom_right")
        self.layout_bottom_right.setContentsMargins(0, 1, 0, 0)
        self.spacer_bottom_right = QSpacerItem(0, 0, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.layout_bottom_right.addItem(self.spacer_bottom_right)

        self.slider_thumbnails = QSlider(self.widget_bottom_right)
        self.slider_thumbnails.setObjectName(u"slider_thumbnails")
        self.slider_thumbnails.setMinimumSize(QSize(150, 0))
        self.slider_thumbnails.setMaximumSize(QSize(250, 16777215))
        self.slider_thumbnails.setOrientation(Qt.Horizontal)

        self.layout_bottom_right.addWidget(self.slider_thumbnails)


        self.layout_main_bottom.addWidget(self.widget_bottom_right)

        self.layout_main_bottom.setStretch(0, 1)
        self.layout_main_bottom.setStretch(2, 1)

        self.layout_central_area.addWidget(self.frame_main_bottom)

        self.splitter_main.addWidget(self.widget_central_area)
        self.widget_sidebar_metadata = QWidget(self.splitter_main)
        self.widget_sidebar_metadata.setObjectName(u"widget_sidebar_metadata")
        self.widget_sidebar_metadata.setMinimumSize(QSize(180, 0))
        self.widget_sidebar_metadata.setMaximumSize(QSize(500, 16777215))
        self.layout_sidebar_metadata = QVBoxLayout(self.widget_sidebar_metadata)
        self.layout_sidebar_metadata.setSpacing(6)
        self.layout_sidebar_metadata.setObjectName(u"layout_sidebar_metadata")
        self.layout_sidebar_metadata.setContentsMargins(0, 0, 0, 0)
        self.stacked_widget_sidebar_metadata = QStackedWidget(self.widget_sidebar_metadata)
        self.stacked_widget_sidebar_metadata.setObjectName(u"stacked_widget_sidebar_metadata")
        self.page_metadata_default = QWidget()
        self.page_metadata_default.setObjectName(u"page_metadata_default")
        self.layout_page_metadata_default = QVBoxLayout(self.page_metadata_default)
        self.layout_page_metadata_default.setObjectName(u"layout_page_metadata_default")
        self.layout_page_metadata_default.setContentsMargins(0, 0, 0, 0)
        self.lbl_metadata_placeholder = QLabel(self.page_metadata_default)
        self.lbl_metadata_placeholder.setObjectName(u"lbl_metadata_placeholder")
        self.lbl_metadata_placeholder.setAlignment(Qt.AlignCenter)

        self.layout_page_metadata_default.addWidget(self.lbl_metadata_placeholder)

        self.stacked_widget_sidebar_metadata.addWidget(self.page_metadata_default)

        self.layout_sidebar_metadata.addWidget(self.stacked_widget_sidebar_metadata)

        self.splitter_main.addWidget(self.widget_sidebar_metadata)

        self.layout_content.addWidget(self.splitter_main)


        self.layout_central_main.addLayout(self.layout_content)

        self.frame_separator_bottom = QFrame(self.widget_central_main)
        self.frame_separator_bottom.setObjectName(u"frame_separator_bottom")
        self.frame_separator_bottom.setFrameShape(QFrame.HLine)
        self.frame_separator_bottom.setFrameShadow(QFrame.Sunken)

        self.layout_central_main.addWidget(self.frame_separator_bottom)

        MainWindow.setCentralWidget(self.widget_central_main)
        self.menubar = QMenuBar(MainWindow)
        self.menubar.setObjectName(u"menubar")
        self.menubar.setGeometry(QRect(0, 0, 1200, 21))
        self.menu_file = QMenu(self.menubar)
        self.menu_file.setObjectName(u"menu_file")
        self.menu_help = QMenu(self.menubar)
        self.menu_help.setObjectName(u"menu_help")
        MainWindow.setMenuBar(self.menubar)
        self.statusbar = QStatusBar(MainWindow)
        self.statusbar.setObjectName(u"statusbar")
        self.statusbar.setMinimumSize(QSize(0, 24))
        MainWindow.setStatusBar(self.statusbar)

        self.menubar.addAction(self.menu_file.menuAction())
        self.menubar.addAction(self.menu_help.menuAction())
        self.menu_file.addAction(self.action_load_folder)
        self.menu_file.addSeparator()
        self.menu_file.addAction(self.action_new_catalog)
        self.menu_file.addAction(self.action_open_catalog)
        self.menu_file.addSeparator()
        self.menu_file.addAction(self.action_add_folder)
        self.menu_file.addAction(self.action_add_files)
        self.menu_file.addSeparator()
        self.menu_file.addAction(self.action_convert_format)
        self.menu_file.addSeparator()
        self.menu_file.addAction(self.action_exit)
        self.menu_help.addAction(self.action_about)

        self.retranslateUi(MainWindow)

        self.stacked_widget_sidebar_catalog.setCurrentIndex(0)
        self.stacked_widget_main.setCurrentIndex(1)
        self.stacked_widget_sidebar_metadata.setCurrentIndex(0)


        QMetaObject.connectSlotsByName(MainWindow)
    # setupUi

    def retranslateUi(self, MainWindow):
        MainWindow.setWindowTitle(QCoreApplication.translate("MainWindow", u"Catalogador Multimedia", None))
        self.action_load_folder.setText(QCoreApplication.translate("MainWindow", u"Mostrar im\u00e1genes de una carpeta", None))
        self.action_exit.setText(QCoreApplication.translate("MainWindow", u"Salir", None))
#if QT_CONFIG(shortcut)
        self.action_exit.setShortcut(QCoreApplication.translate("MainWindow", u"Ctrl+Q", None))
#endif // QT_CONFIG(shortcut)
        self.action_about.setText(QCoreApplication.translate("MainWindow", u"Acerca de...", None))
        self.action_new_catalog.setText(QCoreApplication.translate("MainWindow", u"Nuevo cat\u00e1logo", None))
        self.action_save.setText(QCoreApplication.translate("MainWindow", u"Guardar", None))
        self.action_save_as.setText(QCoreApplication.translate("MainWindow", u"Guardar como...", None))
        self.action_convert_format.setText(QCoreApplication.translate("MainWindow", u"Convertir formato", None))
        self.action_add_files.setText(QCoreApplication.translate("MainWindow", u"A\u00f1adir archivos al cat\u00e1logo", None))
        self.action_add_folder.setText(QCoreApplication.translate("MainWindow", u"A\u00f1adir carpeta al cat\u00e1logo", None))
        self.action_open_catalog.setText(QCoreApplication.translate("MainWindow", u"Abrir cat\u00e1logo", None))
#if QT_CONFIG(tooltip)
        self.btn_catalog.setToolTip(QCoreApplication.translate("MainWindow", u"Cat\u00e1logo", None))
#endif // QT_CONFIG(tooltip)
#if QT_CONFIG(tooltip)
        self.btn_image.setToolTip(QCoreApplication.translate("MainWindow", u"Imagen", None))
#endif // QT_CONFIG(tooltip)
#if QT_CONFIG(tooltip)
        self.btn_video.setToolTip(QCoreApplication.translate("MainWindow", u"V\u00eddeo", None))
#endif // QT_CONFIG(tooltip)
#if QT_CONFIG(tooltip)
        self.btn_audio.setToolTip(QCoreApplication.translate("MainWindow", u"Audio", None))
#endif // QT_CONFIG(tooltip)
#if QT_CONFIG(tooltip)
        self.btn_settings.setToolTip(QCoreApplication.translate("MainWindow", u"Ajustes", None))
#endif // QT_CONFIG(tooltip)
        self.lbl_metadata_placeholder.setText(QCoreApplication.translate("MainWindow", u"Metadata sidebar...", None))
        self.menu_file.setTitle(QCoreApplication.translate("MainWindow", u"Archivo", None))
        self.menu_help.setTitle(QCoreApplication.translate("MainWindow", u"Ayuda", None))
    # retranslateUi
