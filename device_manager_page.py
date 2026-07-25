
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime
import traceback

from gui.central_preview import CentralPreview
import modules.camera_db as camera_db

from .auto_search_window import AutoSearchWindow
from .constants import COLOR_BG, COLOR_WHITE
from .camera_card import CameraCard


class DeviceManagerPage(tk.Frame):
    """
    Device Manager page.

    IMPORTANT ARCHITECTURE:

        CameraApp
            |
            +-- Owns Camera objects
            +-- Owns camera stream lifecycle
            +-- Starts/stops cameras according to status
            +-- Handles camera registration/removal
            |
            +-----------------------------+
            |                             |
        MainPage                   DeviceManagerPage
        (display only)             (management only)

    This page MUST NOT:

        camera.start()
        camera.stop()

    CameraApp is the only component that controls shared
    camera streams.

    A camera with status=False is considered disabled/under
    maintenance and must not have an active stream.
    """

    # =========================================================
    # LAYOUT CONFIGURATION
    # =========================================================

    LEFT_PANEL_WIDTH = 320
    RIGHT_PANEL_WIDTH = 320

    MIN_LEFT_WIDTH = 250
    MIN_RIGHT_WIDTH = 240

    MIN_CENTER_WIDTH = 400
    MIN_CENTER_HEIGHT = 250

    CAMERA_ASPECT_RATIO = 16 / 9

    # =========================================================
    # INIT
    # =========================================================

    def __init__(self, parent, controller):

        super().__init__(
            parent,
            bg=COLOR_BG
        )

        self.controller = controller

        # =====================================================
        # PAGE STATE
        # =====================================================

        self.is_visible = False

        self.add_panel_showing = False
        self.settings_panel_showing = False

        # =====================================================
        # CAMERA DATA
        # =====================================================

        # IMPORTANT:
        #
        # This is only a reference/cache for the shared
        # Camera objects owned by CameraApp.
        #
        # We NEVER create another Camera registry here.
        #
        self.cameras = []

        self.camera_cards = {}

        # =====================================================
        # BUILD UI
        # =====================================================

        self._build_ui()

        # =====================================================
        # USE CONTROLLER CAMERA REGISTRY
        # =====================================================

        self.load_existing_cameras()

        # =====================================================
        # PLC
        # =====================================================

        self.plc_reader = None

        try:

            from modules.plc_reader import PLCReader

            self.plc_reader = PLCReader()

            self.central_frame.set_plc(
                self.plc_reader
            )

            self.central_frame.start()

        except Exception as e:

            print(
                "PLC Initialization "
                f"Skipped/Failed: {e}"
            )

    # =========================================================
    # PAGE LIFECYCLE
    # =========================================================

    def tkraise(
        self,
        *args,
        **kwargs
    ):

        super().tkraise(
            *args,
            **kwargs
        )

        self.on_show()

    # =========================================================

    def on_show(self):

        self.is_visible = True

        # =====================================================
        # REFRESH SHARED CAMERA REFERENCES
        # =====================================================

        self.load_existing_cameras(
            refresh_cards=True
        )

        # =====================================================
        # REFRESH CENTRAL PREVIEW
        # =====================================================

        if hasattr(
            self,
            "central_frame"
        ):

            try:

                if hasattr(
                    self.central_frame,
                    "reload_cameras"
                ):

                    self.central_frame.reload_cameras()

            except Exception as e:

                print(
                    "Central preview refresh error:",
                    e
                )

    # =========================================================

    def hide(
        self
    ):

        self.on_hide()

    # =========================================================

    def on_hide(
        self
    ):

        """
        Hide the page.

        IMPORTANT:

        This function does NOT stop cameras.

        CameraApp owns all shared camera streams.

        Streams continue running while switching between
        MainPage and DeviceManagerPage.

        Only page-specific resources should be stopped here.
        """

        self.is_visible = False

        # =====================================================
        # DO NOT STOP CAMERAS
        # =====================================================
        #
        # NEVER DO:
        #
        #     cam.stop()
        #
        # CameraApp owns camera lifecycle.
        #

        # =====================================================
        # PAGE-SPECIFIC RESOURCES
        # =====================================================
        #
        # CentralPreview/PLC is page-specific.
        #
        # If CentralPreview itself has a stop method, it may
        # stop its PLC monitoring here.
        #
        # It must NOT stop shared camera streams.
        #

        if hasattr(
            self,
            "central_frame"
        ):

            try:

                if hasattr(
                    self.central_frame,
                    "stop"
                ):

                    self.central_frame.stop()

            except Exception as e:

                print(
                    "Central preview cleanup error:",
                    e
                )

    # =========================================================
    # UI CONSTRUCTION
    # =========================================================

    def _build_ui(
        self
    ):

        # =====================================================
        # ROOT GRID
        # =====================================================

        self.grid_rowconfigure(
            0,
            weight=0
        )

        self.grid_rowconfigure(
            1,
            weight=0
        )

        self.grid_rowconfigure(
            2,
            weight=1
        )

        self.grid_columnconfigure(
            0,
            weight=0,
            minsize=self.MIN_LEFT_WIDTH
        )

        self.grid_columnconfigure(
            1,
            weight=0,
            minsize=10
        )

        self.grid_columnconfigure(
            2,
            weight=1,
            minsize=self.MIN_CENTER_WIDTH
        )

        self.grid_columnconfigure(
            3,
            weight=0,
            minsize=self.MIN_RIGHT_WIDTH
        )

        # =====================================================
        # TOP BAR
        # =====================================================

        self._create_back_bar()

        self._create_title()

        # =====================================================
        # LEFT PANEL
        # =====================================================

        self._create_left_sidebar()

        # =====================================================
        # CENTER
        # =====================================================

        self.center_container = tk.Frame(
            self,
            bg=COLOR_BG
        )

        self.center_container.grid(
            row=2,
            column=2,
            sticky="nsew",
            padx=10,
            pady=10
        )

        self.center_container.grid_propagate(
            False
        )

        self.center_container.pack_propagate(
            False
        )

        # =====================================================
        # CENTRAL PREVIEW
        # =====================================================

        self.central_frame = CentralPreview(
            self.center_container,
            self
        )

        self.central_frame.pack(
            fill="both",
            expand=True
        )

        # =====================================================
        # RESPONSIVE CENTER
        # =====================================================

        self.center_container.bind(
            "<Configure>",
            self._resize_center_preview
        )

        # =====================================================
        # RIGHT PANEL
        # =====================================================

        self._create_right_panel()

    # =========================================================
    # BACK BAR
    # =========================================================

    def _create_back_bar(
        self
    ):

        back_bar = tk.Frame(
            self,
            bg=COLOR_BG
        )

        back_bar.grid(
            row=0,
            column=0,
            columnspan=4,
            sticky="ew",
            padx=10,
            pady=(5, 0)
        )

        back_box = tk.Frame(
            back_bar,
            bg="white",
            bd=2,
            relief="groove"
        )

        back_box.pack(
            anchor="w"
        )

        tk.Button(
            back_box,
            text="⬅ Back",
            font=(
                "Arial",
                10,
                "bold"
            ),
            bg="white",
            fg="black",
            bd=0,
            relief="flat",
            padx=10,
            pady=5,
            command=lambda:
                self.controller.show_frame(
                    "MainPage"
                )
        ).pack()

    # =========================================================
    # TITLE
    # =========================================================

    def _create_title(
        self
    ):

        title_frame = tk.Frame(
            self,
            bg=COLOR_BG
        )

        title_frame.grid(
            row=1,
            column=0,
            columnspan=4,
            sticky="ew"
        )

        tk.Label(
            title_frame,
            text="Settings",
            font=(
                "Arial",
                24,
                "bold"
            ),
            bg=COLOR_BG,
            fg="white"
        ).pack(
            pady=10
        )

    # =========================================================
    # LEFT SIDEBAR
    # =========================================================

    def _create_left_sidebar(
        self
    ):

        self.left_container = tk.Frame(
            self,
            bg=COLOR_BG
        )

        self.left_container.grid(
            row=2,
            column=0,
            sticky="nsew",
            padx=(20, 5),
            pady=(0, 10)
        )

        self.left_container.grid_columnconfigure(
            0,
            weight=1
        )

        self.left_container.grid_rowconfigure(
            1,
            weight=1
        )

        # =====================================================
        # TOP BUTTONS
        # =====================================================

        button_frame = tk.Frame(
            self.left_container,
            bg=COLOR_BG
        )

        button_frame.grid(
            row=0,
            column=0,
            sticky="ew",
            pady=(0, 10)
        )

        button_frame.grid_columnconfigure(
            0,
            weight=1
        )

        button_frame.grid_columnconfigure(
            1,
            weight=1
        )

        self.add_btn = tk.Button(
            button_frame,
            text="+ Add Device",
            relief="flat",
            bd=1,
            activebackground="white",
            activeforeground="black",
            font=(
                "Arial",
                11,
                "bold"
            ),
            command=self.show_add_panel
        )

        self.add_btn.grid(
            row=0,
            column=0,
            sticky="ew",
            padx=(0, 3),
            ipady=5
        )

        self.settings_btn = tk.Button(
            button_frame,
            text="⚙️ System Settings",
            relief="flat",
            bd=1,
            activebackground="white",
            activeforeground="black",
            font=(
                "Arial",
                11,
                "bold"
            ),
            command=self.show_settings_panel
        )

        self.settings_btn.grid(
            row=0,
            column=1,
            sticky="ew",
            padx=(3, 0),
            ipady=5
        )

        # =====================================================
        # ADD PANEL
        # =====================================================

        self.left_panel = tk.Frame(
            self.left_container,
            bg=COLOR_WHITE,
            bd=2,
            relief="groove"
        )

        self.left_panel.grid(
            row=1,
            column=0,
            sticky="nsew"
        )

        self.left_panel.grid_remove()

        self._build_add_panel()

        # =====================================================
        # SETTINGS PANEL
        # =====================================================

        self.settings_panel = tk.Frame(
            self.left_container,
            bg=COLOR_WHITE,
            bd=2,
            relief="groove"
        )

        self.settings_panel.grid(
            row=1,
            column=0,
            sticky="nsew"
        )

        self.settings_panel.grid_remove()

        self._build_settings_panel()

    # =========================================================
    # ADD PANEL
    # =========================================================

    def _build_add_panel(
        self
    ):

        self.left_panel.grid_columnconfigure(
            1,
            weight=1
        )

        self.zone_label = tk.Label(
            self.left_panel,
            text="zone # --",
            bg=COLOR_WHITE,
            fg="black",
            font=(
                "Arial",
                12,
                "bold"
            )
        )

        self.zone_label.grid(
            row=0,
            column=0,
            columnspan=2,
            sticky="w",
            padx=20,
            pady=(10, 5)
        )

        fields = [
            "Name",
            "IP",
            "port",
            "username",
            "password"
        ]

        self.entries = {}

        for i, field in enumerate(fields):

            tk.Label(
                self.left_panel,
                text=f"{field}:",
                bg=COLOR_WHITE,
                fg="black",
                font=(
                    "Arial",
                    10,
                    "bold"
                )
            ).grid(
                row=i + 1,
                column=0,
                sticky="w",
                padx=(10, 5),
                pady=5
            )

            entry = tk.Entry(
                self.left_panel,
                font=(
                    "Arial",
                    10
                )
            )

            if field == "password":

                entry.config(
                    show="*"
                )

            entry.grid(
                row=i + 1,
                column=1,
                sticky="ew",
                padx=(5, 20),
                pady=5
            )

            entry.config(
                highlightbackground="gray",
                highlightcolor="gray",
                highlightthickness=1
            )

            self.entries[field] = entry

        # =====================================================
        # ENABLED / MAINTENANCE STATUS
        # =====================================================

        tk.Label(
            self.left_panel,
            text="Status:",
            bg=COLOR_WHITE,
            fg="black",
            font=(
                "Arial",
                10,
                "bold"
            )
        ).grid(
            row=6,
            column=0,
            sticky="w",
            padx=(10, 5),
            pady=8
        )

        self.popup_var = tk.StringVar(
            value="Yes"
        )

        popup_frame = tk.Frame(
            self.left_panel,
            bg=COLOR_WHITE
        )

        popup_frame.grid(
            row=6,
            column=1,
            sticky="w",
            padx=10,
            pady=3
        )

        tk.Radiobutton(
            popup_frame,
            text="Enabled",
            variable=self.popup_var,
            value="Yes",
            bg=COLOR_WHITE
        ).pack(
            side="left",
            padx=(0, 15)
        )

        tk.Radiobutton(
            popup_frame,
            text="Maintenance",
            variable=self.popup_var,
            value="No",
            bg=COLOR_WHITE
        ).pack(
            side="left"
        )

        # =====================================================
        # AUTO SEARCH
        # =====================================================

        tk.Button(
            self.left_panel,
            text="AUTO SEARCH",
            bg="white",
            fg="black",
            width=25,
            command=self.open_auto_search_window
        ).grid(
            row=7,
            column=0,
            columnspan=2,
            pady=(10, 10)
        )

        # =====================================================
        # BUTTONS
        # =====================================================

        btn_frame = tk.Frame(
            self.left_panel,
            bg=COLOR_WHITE
        )

        btn_frame.grid(
            row=8,
            column=0,
            columnspan=2,
            padx=20,
            pady=(10, 20),
            sticky="ew"
        )

        btn_frame.grid_columnconfigure(
            0,
            weight=1
        )

        btn_frame.grid_columnconfigure(
            1,
            weight=1
        )

        tk.Button(
            btn_frame,
            text="ADD",
            bg="white",
            fg="black",
            command=self.add_camera_to_db
        ).grid(
            row=0,
            column=0,
            sticky="ew",
            padx=5
        )

        tk.Button(
            btn_frame,
            text="CANCEL",
            bg="white",
            fg="black",
            command=self.hide_add_panel
        ).grid(
            row=0,
            column=1,
            sticky="ew",
            padx=5
        )

    # =========================================================
    # RIGHT PANEL
    # =========================================================

    def _create_right_panel(
        self
    ):

        self.right_panel = tk.Frame(
            self,
            bg=COLOR_WHITE,
            bd=2,
            relief="groove"
        )

        self.right_panel.grid(
            row=2,
            column=3,
            sticky="nsew",
            padx=(5, 20),
            pady=(0, 10)
        )

        self.right_panel.grid_propagate(
            False
        )

        tk.Label(
            self.right_panel,
            text="Connected Devices",
            font=(
                "Arial",
                14,
                "bold"
            ),
            bg=COLOR_WHITE,
            fg="black"
        ).pack(
            pady=10
        )

        scroll_area = tk.Frame(
            self.right_panel,
            bg=COLOR_WHITE
        )

        scroll_area.pack(
            fill="both",
            expand=True,
            padx=(8, 0),
            pady=(0, 8)
        )

        self.camera_canvas = tk.Canvas(
            scroll_area,
            bg=COLOR_WHITE,
            highlightthickness=0,
            bd=0
        )

        self.camera_canvas.pack(
            side="left",
            fill="both",
            expand=True
        )

        self.camera_scrollbar = tk.Scrollbar(
            scroll_area,
            orient="vertical",
            command=self.camera_canvas.yview
        )

        self.camera_scrollbar.pack(
            side="right",
            fill="y"
        )

        self.camera_canvas.configure(
            yscrollcommand=self.camera_scrollbar.set
        )

        self.scrollable_frame = tk.Frame(
            self.camera_canvas,
            bg=COLOR_WHITE
        )

        self.canvas_window = (
            self.camera_canvas.create_window(
                (0, 0),
                window=self.scrollable_frame,
                anchor="nw"
            )
        )

        self.scrollable_frame.bind(
            "<Configure>",
            self._update_camera_scroll_region
        )

        self.camera_canvas.bind(
            "<Configure>",
            self._resize_scrollable_frame
        )

        self.right_panel.bind(
            "<MouseWheel>",
            self._on_camera_mousewheel,
            add="+"
        )

        self.camera_canvas.bind(
            "<MouseWheel>",
            self._on_camera_mousewheel,
            add="+"
        )

        self.scrollable_frame.bind(
            "<MouseWheel>",
            self._on_camera_mousewheel,
            add="+"
        )

        self.bind_all(
            "<MouseWheel>",
            self._on_global_camera_mousewheel,
            add="+"
        )

    # =========================================================
    # SCROLL HELPERS
    # =========================================================

    def _update_camera_scroll_region(
        self,
        event=None
    ):

        try:

            self.camera_canvas.configure(
                scrollregion=(
                    self.camera_canvas.bbox(
                        "all"
                    )
                )
            )

        except tk.TclError:

            pass

    # =========================================================

    def _resize_scrollable_frame(
        self,
        event
    ):

        try:

            self.camera_canvas.itemconfigure(
                self.canvas_window,
                width=event.width
            )

        except tk.TclError:

            pass

    # =========================================================

    def _is_pointer_inside_right_panel(
        self
    ):

        try:

            x = self.winfo_pointerx()
            y = self.winfo_pointery()

            widget = self.winfo_containing(
                x,
                y
            )

            if widget is None:

                return False

            current = widget

            while current is not None:

                if current == self.right_panel:

                    return True

                current = getattr(
                    current,
                    "master",
                    None
                )

        except Exception:

            return False

        return False

    # =========================================================

    def _on_global_camera_mousewheel(
        self,
        event
    ):

        if not self.is_visible:

            return

        if not self._is_pointer_inside_right_panel():

            return

        if event.delta == 0:

            return

        self.camera_canvas.yview_scroll(
            int(
                -event.delta / 120
            ),
            "units"
        )

    # =========================================================

    def _on_camera_mousewheel(
        self,
        event
    ):

        if event.delta == 0:

            return "break"

        self.camera_canvas.yview_scroll(
            int(
                -event.delta / 120
            ),
            "units"
        )

        return "break"

    # =========================================================

    def _scroll_camera_list(
        self,
        amount
    ):

        self.camera_canvas.yview_scroll(
            amount,
            "units"
        )

        return "break"

    # =========================================================
    # CENTER PREVIEW
    # =========================================================

    def _resize_center_preview(
        self,
        event=None
    ):

        if not hasattr(
            self,
            "central_frame"
        ):

            return

        available_width = (
            self.center_container.winfo_width()
        )

        available_height = (
            self.center_container.winfo_height()
        )

        if (
            available_width <= 1
            or available_height <= 1
        ):

            return

        preview_width = available_width

        preview_height = (
            preview_width
            / self.CAMERA_ASPECT_RATIO
        )

        if preview_height > available_height:

            preview_height = available_height

            preview_width = (
                preview_height
                * self.CAMERA_ASPECT_RATIO
            )

        x = (
            available_width
            - preview_width
        ) / 2

        y = (
            available_height
            - preview_height
        ) / 2

        self.central_frame.place(
            x=int(x),
            y=int(y),
            width=max(
                1,
                int(preview_width)
            ),
            height=max(
                1,
                int(preview_height)
            )
        )

    # =========================================================
    # CAMERA REGISTRY
    # =========================================================

    def load_existing_cameras(
        self,
        refresh_cards=True
    ):

        """
        Load camera references from CameraApp.

        IMPORTANT:

        This does NOT call camera_db.load_all_cameras().

        CameraApp owns the Camera objects.
        """

        try:

            if hasattr(
                self.controller,
                "get_cameras"
            ):

                self.cameras = (
                    self.controller
                    .get_cameras()
                )

            else:

                self.cameras = list(
                    getattr(
                        self.controller,
                        "cameras",
                        []
                    )
                )

        except Exception as e:

            print(
                "Failed to get cameras "
                f"from CameraApp: {e}"
            )

            self.cameras = []

        if not refresh_cards:

            return

        # =====================================================
        # REMOVE CARDS FOR DELETED CAMERAS
        # =====================================================

        valid_ids = {
            cam.id
            for cam in self.cameras
            if cam is not None
        }

        for camera_id in list(
            self.camera_cards.keys()
        ):

            if camera_id not in valid_ids:

                card = self.camera_cards.pop(
                    camera_id
                )

                try:

                    card.destroy()

                except Exception:

                    pass

        # =====================================================
        # CREATE / REFRESH CARDS
        # =====================================================

        for cam in self.cameras:

            if cam is None:

                continue

            if cam.id not in self.camera_cards:

                self.add_camera_card(
                    cam
                )

            else:

                card = self.camera_cards[
                    cam.id
                ]

                try:

                    if hasattr(
                        card,
                        "update_info"
                    ):

                        card.update_info()

                    elif hasattr(
                        card,
                        "refresh"
                    ):

                        card.refresh()

                except Exception as e:

                    print(
                        "Camera card refresh error:",
                        e
                    )

    # =========================================================
    # CAMERA CARDS
    # =========================================================

    def add_camera_card(
        self,
        cam
    ):

        if cam is None:

            return

        if cam.id in self.camera_cards:

            return

        card = CameraCard(
            parent=self.scrollable_frame,
            cam=cam,
            controller=self,
            on_delete_callback=self._on_card_deleted
        )

        self.camera_cards[
            cam.id
        ] = card

        self._bind_mousewheel_recursive(
            card
        )

        self.after_idle(
            self._update_camera_scroll_region
        )

    # =========================================================

    def _bind_mousewheel_recursive(
        self,
        widget
    ):

        try:

            widget.bind(
                "<MouseWheel>",
                self._on_camera_mousewheel,
                add="+"
            )

        except Exception:

            pass

        try:

            for child in widget.winfo_children():

                self._bind_mousewheel_recursive(
                    child
                )

        except Exception:

            pass

    # =========================================================
    # ADD PANEL
    # =========================================================

    def show_add_panel(
        self
    ):

        if self.add_panel_showing:

            self.hide_add_panel()

            return

        self.settings_panel.grid_remove()

        self.settings_panel_showing = False

        try:

            next_zone = (
                camera_db.get_next_modbus()
            )

            self.zone_label.configure(
                text=f"zone # {next_zone}"
            )

        except Exception:

            self.zone_label.configure(
                text="zone # --"
            )

        self.left_panel.grid()

        self.add_panel_showing = True

    # =========================================================

    def hide_add_panel(
        self
    ):

        self.left_panel.grid_remove()

        self.add_panel_showing = False

        self.clear_entries()

    # =========================================================
    # SETTINGS PANEL
    # =========================================================

    def _build_settings_panel(
        self
    ):

        self.settings_content = tk.Frame(
            self.settings_panel,
            bg="white"
        )

        self.settings_content.pack(
            fill="both",
            expand=True
        )

        tk.Label(
            self.settings_content,
            text="System Settings",
            bg="white",
            fg="black",
            font=(
                "Arial",
                13,
                "bold"
            )
        ).pack(
            pady=(15, 20)
        )

        screen_box = tk.LabelFrame(
            self.settings_content,
            text="Screen view",
            bg="white",
            padx=10,
            pady=10
        )

        screen_box.pack(
            fill="x",
            padx=15,
            pady=5
        )

        self.screen_view = tk.StringVar(
            value="4"
        )

        tk.Radiobutton(
            screen_box,
            text="4 Cameras",
            variable=self.screen_view,
            value="4",
            bg="white",
            command=self.change_screen_view
        ).pack(
            anchor="w"
        )

        tk.Radiobutton(
            screen_box,
            text="8 Cameras",
            variable=self.screen_view,
            value="8",
            bg="white",
            command=self.change_screen_view
        ).pack(
            anchor="w"
        )

        tk.Label(
            self.settings_content,
            text="Date & Time",
            bg="white",
            fg="black",
            font=(
                "Arial",
                11,
                "bold"
            )
        ).pack(
            anchor="w",
            padx=15,
            pady=(20, 8)
        )

        tk.Label(
            self.settings_content,
            text="Date",
            bg="white",
            fg="black"
        ).pack(
            anchor="w",
            padx=30
        )

        self.date_entry = tk.Entry(
            self.settings_content,
            width=18,
            justify="left"
        )

        self.date_entry.pack(
            padx=15,
            pady=(2, 8),
            anchor="w"
        )

        tk.Label(
            self.settings_content,
            text="Time",
            bg="white",
            fg="black"
        ).pack(
            anchor="w",
            padx=30
        )

        self.time_entry = tk.Entry(
            self.settings_content,
            width=18,
            justify="left"
        )

        self.time_entry.pack(
            padx=15,
            pady=(2, 10),
            anchor="w"
        )

        now = datetime.now()

        self.date_entry.insert(
            0,
            now.strftime(
                "%Y/%m/%d"
            )
        )

        self.time_entry.insert(
            0,
            now.strftime(
                "%H:%M:%S"
            )
        )

        lang_box = tk.LabelFrame(
            self.settings_content,
            text="Language",
            bg="white",
            padx=10,
            pady=10
        )

        lang_box.pack(
            fill="x",
            padx=15,
            pady=5
        )

        self.language = tk.StringVar(
            value="English"
        )

        ttk.Combobox(
            lang_box,
            textvariable=self.language,
            values=[
                "English",
                "فارسی"
            ],
            state="readonly"
        ).pack(
            fill="x"
        )

        tk.Button(
            self.settings_content,
            text="Save",
            width=18,
            bg="#2E8B57",
            fg="white",
            font=(
                "Arial",
                11,
                "bold"
            ),
            command=self.save_settings
        ).pack(
            pady=20
        )

    # =========================================================

    def show_settings_panel(
        self
    ):

        if self.settings_panel_showing:

            self.settings_panel.grid_remove()

            self.settings_panel_showing = False

            return

        self.left_panel.grid_remove()

        self.add_panel_showing = False

        self.settings_panel.grid()

        self.settings_panel_showing = True

    # =========================================================

    def change_screen_view(
        self
    ):

        try:

            view = int(
                self.screen_view.get()
            )

        except ValueError:

            return

        if hasattr(
            self.controller,
            "change_screen_view"
        ):

            self.controller.change_screen_view(
                view
            )

    # =========================================================
    # CLEAR FORM
    # =========================================================

    def clear_entries(
        self
    ):

        for entry in self.entries.values():

            entry.config(
                highlightbackground="gray",
                highlightcolor="gray",
                highlightthickness=1
            )

            entry.delete(
                0,
                tk.END
            )

        self.popup_var.set(
            "Yes"
        )

    # =========================================================
    # ADD CAMERA
    # =========================================================

    def add_camera_to_db(
        self
    ):

        name = (
            self.entries[
                "Name"
            ].get().strip()
        )

        ip = (
            self.entries[
                "IP"
            ].get().strip()
        )

        port_raw = (
            self.entries[
                "port"
            ].get().strip()
        )

        username = (
            self.entries[
                "username"
            ].get().strip()
        )

        password = (
            self.entries[
                "password"
            ].get().strip()
        )

        # =====================================================
        # RESET VALIDATION
        # =====================================================

        for entry in self.entries.values():

            entry.config(
                highlightbackground="gray",
                highlightcolor="gray",
                highlightthickness=1
            )

        # =====================================================
        # IP
        # =====================================================

        if not ip:

            self.entries[
                "IP"
            ].config(
                highlightbackground="red",
                highlightcolor="red",
                highlightthickness=2
            )

            return

        # =====================================================
        # PORT
        # =====================================================

        if port_raw:

            try:

                port = int(
                    port_raw
                )

                if not (
                    1 <= port <= 65535
                ):

                    raise ValueError

            except ValueError:

                self.entries[
                    "port"
                ].config(
                    highlightbackground="red",
                    highlightcolor="red",
                    highlightthickness=2
                )

                messagebox.showwarning(
                    "Invalid Port",
                    "Port must be between 1 and 65535."
                )

                return

        else:

            port = 554

        # =====================================================
        # DUPLICATE IP
        # =====================================================

        try:

            if camera_db.camera_exists(
                ip
            ):

                self.entries[
                    "IP"
                ].config(
                    highlightbackground="red",
                    highlightcolor="red",
                    highlightthickness=2
                )

                messagebox.showwarning(
                    "Duplicate Camera",
                    f"Camera with IP {ip} already exists."
                )

                return

        except Exception:

            pass

        # =====================================================
        # STATUS
        # =====================================================

        status = (
            1
            if self.popup_var.get() == "Yes"
            else 0
        )

        # =====================================================
        # SAVE
        # =====================================================

        try:

            modbus = (
                camera_db.get_next_modbus()
            )

            cam = camera_db.add_camera(
                modbus=modbus,
                ip=ip,
                status=status,
                name=name,
                zone=modbus,
                port=port,
                username=username,
                password=password
            )

            # =================================================
            # REGISTER WITH CAMERA APP
            # =================================================

            if hasattr(
                self.controller,
                "register_camera"
            ):

                cam = (
                    self.controller
                    .register_camera(
                        cam
                    )
                )

            # =================================================
            # UPDATE LOCAL REFERENCES
            # =================================================

            self.load_existing_cameras(
                refresh_cards=True
            )

            # =================================================
            # START ONLY IF ENABLED
            # =================================================

            if (
                status
                and hasattr(
                    self.controller,
                    "start_camera"
                )
            ):

                self.controller.start_camera(
                    cam
                )

            # =================================================
            # UI
            # =================================================

            self.clear_entries()

            self.refresh_modbus_ui()

            self.hide_add_panel()

            self._notify_camera_change()

        except Exception as e:

            traceback.print_exc()

            messagebox.showerror(
                "Database Error",
                str(e)
            )

    # =========================================================
    # EDIT CAMERA
    # =========================================================

    def open_edit_camera_window(
        self,
        cam
    ):

        edit_window = tk.Toplevel(
            self
        )

        edit_window.title(
            "Edit Camera"
        )

        edit_window.geometry(
            "420x580"
        )

        edit_window.resizable(
            False,
            False
        )

        edit_window.configure(
            bg="white"
        )

        edit_window.transient(
            self.winfo_toplevel()
        )

        edit_window.grab_set()

        tk.Label(
            edit_window,
            text="Edit Camera",
            font=(
                "Arial",
                18,
                "bold"
            ),
            bg="white"
        ).pack(
            pady=15
        )

        form = tk.Frame(
            edit_window,
            bg="white"
        )

        form.pack(
            fill="both",
            expand=True,
            padx=30
        )

        entries = {}

        fields = [
            ("Name:", "name"),
            ("IP:", "ip"),
            ("Port:", "port"),
            ("Username:", "username"),
            ("Password:", "password")
        ]

        for i, (
            label_text,
            key
        ) in enumerate(fields):

            tk.Label(
                form,
                text=label_text,
                bg="white"
            ).grid(
                row=i,
                column=0,
                sticky="w",
                pady=8
            )

            entry = tk.Entry(
                form,
                width=32
            )

            if key == "password":

                entry.config(
                    show="*"
                )

            entry.grid(
                row=i,
                column=1,
                pady=8
            )

            entry.config(
                highlightbackground="gray",
                highlightcolor="gray",
                highlightthickness=1
            )

            entries[key] = entry

        entries[
            "name"
        ].insert(
            0,
            cam.name or ""
        )

        entries[
            "ip"
        ].insert(
            0,
            cam.ip or ""
        )

        entries[
            "port"
        ].insert(
            0,
            str(
                cam.port or 554
            )
        )

        entries[
            "username"
        ].insert(
            0,
            cam.username or ""
        )

        entries[
            "password"
        ].insert(
            0,
            cam.password or ""
        )

        # =====================================================
        # STATUS
        # =====================================================

        current_status = getattr(
            cam,
            "status",
            1
        )

        is_enabled = (
            str(
                current_status
            ).lower()
            in (
                "1",
                "true",
                "yes"
            )
        )

        status_var = tk.StringVar(
            value=(
                "Yes"
                if is_enabled
                else "No"
            )
        )

        tk.Label(
            form,
            text="Status:",
            bg="white"
        ).grid(
            row=5,
            column=0,
            sticky="w",
            pady=8
        )

        radio_f = tk.Frame(
            form,
            bg="white"
        )

        radio_f.grid(
            row=5,
            column=1,
            sticky="w"
        )

        tk.Radiobutton(
            radio_f,
            text="Enabled",
            variable=status_var,
            value="Yes",
            bg="white"
        ).pack(
            side="left",
            padx=(0, 15)
        )

        tk.Radiobutton(
            radio_f,
            text="Maintenance",
            variable=status_var,
            value="No",
            bg="white"
        ).pack(
            side="left"
        )

        # =====================================================
        # SAVE
        # =====================================================

        tk.Button(
            edit_window,
            text="SAVE CHANGES",
            bg="white",
            fg="black",
            width=20,
            command=lambda:
                self.save_camera_changes(
                    cam=cam,
                    entries=entries,
                    status_var=status_var,
                    window=edit_window
                )
        ).pack(
            pady=20
        )

        # =====================================================
        # CANCEL
        # =====================================================

        tk.Button(
            edit_window,
            text="CANCEL",
            bg="white",
            fg="black",
            width=20,
            command=edit_window.destroy
        ).pack(
            pady=(0, 15)
        )

    # =========================================================
    # SAVE CAMERA CHANGES
    # =========================================================

    def save_camera_changes(
        self,
        cam,
        entries,
        status_var,
        window
    ):

        name = (
            entries[
                "name"
            ].get().strip()
        )

        ip = (
            entries[
                "ip"
            ].get().strip()
        )

        port_raw = (
            entries[
                "port"
            ].get().strip()
        )

        username = (
            entries[
                "username"
            ].get().strip()
        )

        password = (
            entries[
                "password"
            ].get().strip()
        )

        # =====================================================
        # VALIDATE IP
        # =====================================================

        if not ip:

            entries[
                "ip"
            ].config(
                highlightbackground="red",
                highlightcolor="red",
                highlightthickness=2
            )

            return

        # =====================================================
        # VALIDATE PORT
        # =====================================================

        try:

            port = (
                int(
                    port_raw
                )
                if port_raw
                else 554
            )

            if not (
                1 <= port <= 65535
            ):

                raise ValueError

        except ValueError:

            entries[
                "port"
            ].config(
                highlightbackground="red",
                highlightcolor="red",
                highlightthickness=2
            )

            messagebox.showwarning(
                "Invalid Port",
                "Port must be between 1 and 65535.",
                parent=window
            )

            return

        # =====================================================
        # DUPLICATE IP
        # =====================================================

        if ip != cam.ip:

            try:

                if camera_db.camera_exists(
                    ip
                ):

                    entries[
                        "ip"
                    ].config(
                        highlightbackground="red",
                        highlightcolor="red",
                        highlightthickness=2
                    )

                    messagebox.showwarning(
                        "Duplicate Camera",
                        f"Camera with IP {ip} already exists.",
                        parent=window
                    )

                    return

            except Exception as e:

                print(
                    "Duplicate IP check failed:",
                    e
                )

        # =====================================================
        # NEW STATUS
        # =====================================================

        status = (
            1
            if status_var.get() == "Yes"
            else 0
        )

        # =====================================================
        # CHANGE DETECTION
        # =====================================================

        connection_changed = (
            ip != cam.ip
            or port != cam.port
            or username != (
                cam.username or ""
            )
            or password != (
                cam.password or ""
            )
        )

        metadata_changed = (
            name != (
                cam.name or ""
            )
            or status != int(
                cam.status
            )
        )

        if not (
            connection_changed
            or metadata_changed
        ):

            window.destroy()

            return

        # =====================================================
        # DATABASE UPDATE
        # =====================================================

        try:

            camera_db.update_camera(
                cam.id,
                ip=ip,
                port=port,
                username=username,
                password=password,
                status=status,
                name=name
            )

        except Exception as e:

            traceback.print_exc()

            messagebox.showerror(
                "Database Error",
                f"Failed to save changes:\n{e}",
                parent=window
            )

            return

        # =====================================================
        # UPDATE SHARED OBJECT
        # =====================================================

        #
        # IMPORTANT:
        #
        # We update the SAME Camera object.
        #
        # MainPage, DeviceManagerPage, and CentralPreview
        # all continue using the same object.
        #

        cam.ip = ip
        cam.port = port
        cam.username = username
        cam.password = password
        cam.name = name
        cam.status = status

        # =====================================================
        # REBUILD URL
        # =====================================================

        try:

            if hasattr(
                cam,
                "_update_url"
            ):

                cam._update_url()

        except Exception as e:

            print(
                "Failed to update camera URL:",
                e
            )

        # =====================================================
        # LET CAMERA APP HANDLE STREAM
        # =====================================================

        if hasattr(
            self.controller,
            "update_camera_stream"
        ):

            #
            # Preferred API.
            #
            # CameraApp decides whether the stream must be
            # stopped/restarted based on status and connection.
            #

            self.controller.update_camera_stream(
                cam,
                connection_changed=connection_changed
            )

        else:

            #
            # Compatibility fallback.
            #
            # Still goes through CameraApp.
            #

            if not status:

                if hasattr(
                    self.controller,
                    "stop_camera"
                ):

                    self.controller.stop_camera(
                        cam
                    )

            elif connection_changed:

                if hasattr(
                    self.controller,
                    "stop_camera"
                ):

                    self.controller.stop_camera(
                        cam
                    )

                if hasattr(
                    self.controller,
                    "start_camera"
                ):

                    self.controller.start_camera(
                        cam
                    )

            elif hasattr(
                self.controller,
                "start_camera"
            ):

                self.controller.start_camera(
                    cam
                )

        # =====================================================
        # UPDATE CARD
        # =====================================================

        card = self.camera_cards.get(
            cam.id
        )

        if card:

            try:

                if hasattr(
                    card,
                    "update_info"
                ):

                    card.update_info()

                elif hasattr(
                    card,
                    "refresh"
                ):

                    card.refresh()

            except Exception as e:

                print(
                    "Camera card refresh error:",
                    e
                )

        # =====================================================
        # CLOSE WINDOW
        # =====================================================

        try:

            window.grab_release()

        except Exception:

            pass

        window.destroy()

        # =====================================================
        # REFRESH VIEWS
        # =====================================================

        self.load_existing_cameras(
            refresh_cards=True
        )

        self._notify_camera_change()

    # =========================================================
    # DELETE CAMERA
    # =========================================================

    def _on_card_deleted(
        self,
        cam
    ):

        if cam is None:

            return

        result = messagebox.askyesno(
            "Delete Camera",
            (
                f"Are you sure you want to delete "
                f"camera '{cam.name or cam.ip}'?"
            )
        )

        if not result:

            return

        try:

            # =================================================
            # DATABASE
            # =================================================

            camera_db.delete_camera(
                cam.id
            )

            # =================================================
            # CONTROLLER REGISTRY
            # =================================================

            if hasattr(
                self.controller,
                "unregister_camera"
            ):

                self.controller.unregister_camera(
                    cam.id
                )

            # =================================================
            # REMOVE CARD
            # =================================================

            card = self.camera_cards.pop(
                cam.id,
                None
            )

            if card:

                try:

                    card.destroy()

                except Exception:

                    pass

            # =================================================
            # REFRESH
            # =================================================

            self.load_existing_cameras(
                refresh_cards=True
            )

            self._notify_camera_change()

            self.refresh_modbus_ui()

        except Exception as e:

            traceback.print_exc()

            messagebox.showerror(
                "Delete Error",
                str(e)
            )

    # =========================================================
    # REFRESH MODBUS UI
    # =========================================================

    def refresh_modbus_ui(
        self
    ):

        try:

            next_zone = (
                camera_db.get_next_modbus()
            )

            self.zone_label.configure(
                text=f"zone # {next_zone}"
            )

        except Exception:

            pass

    # =========================================================
    # NOTIFY OTHER VIEWS
    # =========================================================

    def _notify_camera_change(
        self
    ):

        # =====================================================
        # CENTRAL PREVIEW
        # =====================================================

        if hasattr(
            self,
            "central_frame"
        ):

            try:

                if hasattr(
                    self.central_frame,
                    "reload_cameras"
                ):

                    self.central_frame.reload_cameras()

            except Exception as e:

                print(
                    "Central preview reload error:",
                    e
                )

        # =====================================================
        # MAIN PAGE
        # =====================================================

        if (
            hasattr(
                self.controller,
                "frames"
            )
            and
            "MainPage"
            in self.controller.frames
        ):

            main_page = (
                self.controller.frames[
                    "MainPage"
                ]
            )

            try:

                if hasattr(
                    main_page,
                    "reload_cameras"
                ):

                    main_page.reload_cameras()

            except Exception as e:

                print(
                    "Main page reload error:",
                    e
                )

    # =========================================================
    # LEGACY RELOAD API
    # =========================================================

    def reload_all_cameras_from_db(
        self
    ):

        """
        Compatibility method.

        CameraApp remains the source of truth.

        This method asks CameraApp to reload configuration
        instead of creating duplicate Camera objects.
        """

        try:

            if hasattr(
                self.controller,
                "reload_cameras"
            ):

                self.controller.reload_cameras()

            self.load_existing_cameras(
                refresh_cards=True
            )

            self._notify_camera_change()

        except Exception as e:

            print(
                "Failed to reload cameras:",
                e
            )

    # =========================================================
    # AUTO SEARCH
    # =========================================================

    def open_auto_search_window(
        self
    ):

        try:

            AutoSearchWindow(
                self,
                self.controller
            )

        except TypeError:

            try:

                AutoSearchWindow(
                    self
                )

            except Exception as e:

                traceback.print_exc()

                messagebox.showerror(
                    "Auto Search Error",
                    str(e)
                )

        except Exception as e:

            traceback.print_exc()

            messagebox.showerror(
                "Auto Search Error",
                str(e)
            )

    # =========================================================
    # SETTINGS SAVE
    # =========================================================

    def save_settings(
        self
    ):

        """
        Save system settings.

        Extend this method when actual settings persistence
        is implemented.
        """

        messagebox.showinfo(
            "Settings",
            "Settings saved successfully."
        )

    # =========================================================
    # DESTROY
    # =========================================================

    def destroy(
        self
    ):

        """
        Destroy the Device Manager page.

        IMPORTANT:

        This method NEVER stops shared camera streams.

        CameraApp handles camera shutdown during application
        shutdown.

        Only page-owned resources are cleaned up here.
        """

        self.is_visible = False

        # =====================================================
        # REMOVE GLOBAL MOUSE BINDING
        # =====================================================

        try:

            self.unbind_all(
                "<MouseWheel>"
            )

        except Exception:

            pass

        # =====================================================
        # STOP PAGE-OWNED PLC RESOURCE
        # =====================================================

        if self.plc_reader:

            try:

                if hasattr(
                    self.plc_reader,
                    "stop"
                ):

                    self.plc_reader.stop()

            except Exception as e:

                print(
                    "PLC cleanup error:",
                    e
                )

            finally:

                self.plc_reader = None

        # =====================================================
        # DO NOT STOP CAMERAS
        # =====================================================
        #
        # CameraApp.stop_all_cameras() is responsible for
        # application-wide camera shutdown.
        #

        super().destroy()

