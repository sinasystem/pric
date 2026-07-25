# gui/device_manager_page.py

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

    # =========================================================
    # LAYOUT CONFIGURATION
    # =========================================================

    # Preferred width for the left configuration panel.
    LEFT_PANEL_WIDTH = 320

    # Preferred width for the right camera list.
    RIGHT_PANEL_WIDTH = 320

    # Minimum usable width for left panel.
    MIN_LEFT_WIDTH = 250

    # Minimum usable width for right panel.
    MIN_RIGHT_WIDTH = 240

    # Minimum width for central preview.
    MIN_CENTER_WIDTH = 400

    # Minimum height for central preview.
    MIN_CENTER_HEIGHT = 250

    # 16:9 camera aspect ratio.
    CAMERA_ASPECT_RATIO = 16 / 9

    # =========================================================
    # INIT
    # =========================================================

    def __init__(
        self,
        parent,
        controller
    ):
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
        #
        # The Camera object owns the RTSP connection.
        #
        # DeviceManagerPage only keeps references to cameras.
        #
        # DO NOT create separate RTSP stream objects here.
        #
        # =====================================================

        self.cameras = []

        self.camera_cards = {}

        # =====================================================
        # BUILD UI
        # =====================================================

        self._build_ui()

        # =====================================================
        # LOAD CAMERAS
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
        """
        Called when the page becomes visible.
        """

        super().tkraise(
            *args,
            **kwargs
        )

        self.on_show()

    # =========================================================

    def on_show(
        self
    ):
        """
        Start camera workers when Device Manager becomes visible.

        The Camera class owns the actual worker thread.
        """

        self.is_visible = True

        for cam in list(
            self.cameras
        ):

            try:

                if not cam.running:

                    cam.start()

            except Exception as e:

                print(
                    f"Failed to start camera "
                    f"{getattr(cam, 'ip', 'unknown')}: "
                    f"{e}"
                )

        # Refresh central preview.

        if hasattr(
            self,
            "central_frame"
        ):

            if hasattr(
                self.central_frame,
                "reload_cameras"
            ):

                try:

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
        """
        Compatibility alias.
        """

        self.on_hide()

    # =========================================================

    def on_hide(
        self
    ):
        """
        Stop camera workers when leaving Device Manager.

        Camera objects remain in memory.

        They are restarted when the page is shown again.
        """

        self.is_visible = False

        for cam in list(
            self.cameras
        ):

            try:

                if cam.running:

                    cam.stop()

            except Exception as e:

                print(
                    f"Failed to stop camera "
                    f"{getattr(cam, 'ip', 'unknown')}: "
                    f"{e}"
                )

    # =========================================================
    # UI CONSTRUCTION
    # =========================================================

    def _build_ui(
        self
    ):
        """
        Build responsive three-column layout.

        Layout:

            LEFT       CENTER       RIGHT

        The center area gets all extra space.

        The actual camera preview is kept at 16:9.
        """

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
        # RIGHT PANEL
        # =====================================================

        self._create_right_panel()

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

        next_zone = (
            camera_db.get_next_modbus()
        )

        self.zone_label = tk.Label(
            self.left_panel,
            text=f"zone # {next_zone}",
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

        for i, field in enumerate(
            fields
        ):

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

            self.entries[
                field
            ] = entry

        # =====================================================
        # POPUP
        # =====================================================

        tk.Label(
            self.left_panel,
            text="Pop up:",
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
            text="Yes",
            variable=self.popup_var,
            value="Yes",
            bg=COLOR_WHITE
        ).pack(
            side="left",
            padx=(0, 15)
        )

        tk.Radiobutton(
            popup_frame,
            text="No",
            variable=self.popup_var,
            value="No",
            bg=COLOR_WHITE
        ).pack(
            side="left"
        )

        # =====================================================
        # MANUAL INTERVAL
        # =====================================================

        tk.Label(
            self.left_panel,
            text="Manual:",
            bg=COLOR_WHITE,
            fg="black",
            font=(
                "Arial",
                10,
                "bold"
            )
        ).grid(
            row=7,
            column=0,
            sticky="w",
            padx=(10, 5),
            pady=8
        )

        self.manual_interval = ttk.Combobox(
            self.left_panel,
            values=[
                "100s",
                "200s",
                "300s",
                "600s"
            ],
            width=12,
            state="readonly"
        )

        self.manual_interval.grid(
            row=7,
            column=1,
            sticky="w",
            padx=10,
            pady=3
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
            row=8,
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
            row=9,
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

        # =====================================================
        # TITLE
        # =====================================================

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

        # =====================================================
        # SCROLL CONTAINER
        # =====================================================

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

        # =====================================================
        # CANVAS
        # =====================================================

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

        # =====================================================
        # SCROLLBAR
        # =====================================================

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

        # =====================================================
        # SCROLLABLE CONTENT
        # =====================================================

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

        # =====================================================
        # SCROLL REGION
        # =====================================================

        self.scrollable_frame.bind(
            "<Configure>",
            self._update_camera_scroll_region
        )

        # =====================================================
        # KEEP CONTENT WIDTH MATCHED TO CANVAS
        # =====================================================

        self.camera_canvas.bind(
            "<Configure>",
            self._resize_scrollable_frame
        )

        # =====================================================
        # MOUSE WHEEL
        # =====================================================

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

        # Linux
        self.right_panel.bind(
            "<Button-4>",
            lambda e: self._scroll_camera_list(-1),
            add="+"
        )

        self.right_panel.bind(
            "<Button-5>",
            lambda e: self._scroll_camera_list(1),
            add="+"
        )

        self.camera_canvas.bind(
            "<Button-4>",
            lambda e: self._scroll_camera_list(-1),
            add="+"
        )

        self.camera_canvas.bind(
            "<Button-5>",
            lambda e: self._scroll_camera_list(1),
            add="+"
        )

        self.scrollable_frame.bind(
            "<Button-4>",
            lambda e: self._scroll_camera_list(-1),
            add="+"
        )

        self.scrollable_frame.bind(
            "<Button-5>",
            lambda e: self._scroll_camera_list(1),
            add="+"
        )

        # =====================================================
        # GLOBAL MOUSE WHEEL
        # =====================================================
        #
        # This catches mouse wheel events over CameraCard
        # children such as labels/buttons.
        #
        # We only scroll if the pointer is inside right_panel.
        #
        # =====================================================

        self.bind_all(
            "<MouseWheel>",
            self._on_global_camera_mousewheel,
            add="+"
        )

    # =========================================================
    # RIGHT PANEL SCROLL HELPERS
    # =========================================================

    def _update_camera_scroll_region(
        self,
        event=None
    ):

        try:

            self.camera_canvas.configure(
                scrollregion=(
                    self.camera_canvas
                    .bbox("all")
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
        """
        Check whether the mouse pointer is anywhere inside
        the right panel, including empty space and child widgets.
        """

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
    # RESPONSIVE CENTRAL PREVIEW
    # =========================================================

    def _resize_center_preview(
        self,
        event=None
    ):
        """
        Keep the central preview at 16:9.

        The CentralPreview widget itself remains inside the
        center container.

        This prevents its controls from being pushed outside
        the visible window.
        """

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

        # =====================================================
        # Calculate largest 16:9 rectangle.
        # =====================================================

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

        # =====================================================
        # Center preview.
        # =====================================================

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
    # LOAD CAMERAS
    # =========================================================

    def load_existing_cameras(
        self
    ):

        try:

            loaded = (
                camera_db.load_all_cameras()
                or []
            )

        except Exception as e:

            traceback.print_exc()

            messagebox.showerror(
                "Database Error",
                f"Failed to load cameras:\n{e}"
            )

            loaded = []

        self.cameras = list(
            loaded
        )

        # =====================================================
        # SHARE SAME CAMERA OBJECTS WITH CONTROLLER
        # =====================================================

        if hasattr(
            self.controller,
            "cameras"
        ):

            self.controller.cameras = (
                self.cameras
            )

        # =====================================================
        # CREATE CARDS
        # =====================================================

        for cam in self.cameras:

            self.add_camera_card(
                cam
            )

    # =========================================================
    # ADD CAMERA CARD
    # =========================================================

    def add_camera_card(
        self,
        cam
    ):

        if cam is None:

            return

        # =====================================================
        # PREVENT DUPLICATE CARD
        # =====================================================

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

        # =====================================================
        # MOUSE WHEEL
        # =====================================================
        #
        # Bind every child recursively.
        #
        # This is supplementary to bind_all().
        #
        # =====================================================

        self._bind_mousewheel_recursive(
            card
        )

        # =====================================================
        # UPDATE SCROLL REGION
        # =====================================================

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

            widget.bind(
                "<Button-4>",
                lambda e:
                    self._scroll_camera_list(-1),
                add="+"
            )

            widget.bind(
                "<Button-5>",
                lambda e:
                    self._scroll_camera_list(1),
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
    # SHOW ADD PANEL
    # =========================================================

    def show_add_panel(
        self
    ):

        if self.add_panel_showing:

            self.hide_add_panel()

            return

        # Hide settings.

        self.settings_panel.grid_remove()

        self.settings_panel_showing = False

        # Refresh zone number.

        self.zone_label.configure(
            text=(
                f"zone # "
                f"{camera_db.get_next_modbus()}"
            )
        )

        # Show add panel.

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

        self.settings_content.grid_columnconfigure(
            0,
            weight=1
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

        # =====================================================
        # SCREEN VIEW
        # =====================================================

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

        # =====================================================
        # DATE TIME
        # =====================================================

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

        # =====================================================
        # LANGUAGE
        # =====================================================

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

        # =====================================================
        # SAVE
        # =====================================================

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
    # SCREEN VIEW
    # =========================================================

    def change_screen_view(
        self
    ):

        view = int(
            self.screen_view.get()
        )

        if hasattr(
            self.controller,
            "change_screen_view"
        ):

            self.controller.change_screen_view(
                view
            )

    # =========================================================
    # CLEAR ADD FORM
    # =========================================================

    def clear_entries(
        self
    ):

        for entry in (
            self.entries.values()
        ):

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

        for entry in (
            self.entries.values()
        ):

            entry.config(
                highlightbackground="gray",
                highlightcolor="gray",
                highlightthickness=1
            )

        # =====================================================
        # IP REQUIRED
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
                    1
                    <= port
                    <= 65535
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

            if hasattr(
                camera_db,
                "camera_exists"
            ):

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
        # POPUP STATUS
        # =====================================================

        status = (
            1
            if self.popup_var.get()
            == "Yes"
            else 0
        )

        # =====================================================
        # ADD TO DATABASE
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
            # ADD TO SHARED CAMERA LIST
            # =================================================

            if cam not in self.cameras:

                self.cameras.append(
                    cam
                )

            if hasattr(
                self.controller,
                "cameras"
            ):

                self.controller.cameras = (
                    self.cameras
                )

            # =================================================
            # CREATE CARD
            # =================================================

            self.add_camera_card(
                cam
            )

            # =================================================
            # START CAMERA
            # =================================================

            if self.is_visible:

                try:

                    cam.start()

                except Exception as e:

                    print(
                        "Failed to start newly "
                        f"added camera: {e}"
                    )

            # =================================================
            # REFRESH UI
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
    # EDIT CAMERA WINDOW
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

        # =====================================================
        # TITLE
        # =====================================================

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

        # =====================================================
        # FORM
        # =====================================================

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
            (
                "Name:",
                "name"
            ),
            (
                "IP:",
                "ip"
            ),
            (
                "Port:",
                "port"
            ),
            (
                "Username:",
                "username"
            ),
            (
                "Password:",
                "password"
            )
        ]

        for i, (
            label_text,
            key
        ) in enumerate(
            fields
        ):

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

            entries[
                key
            ] = entry

        # =====================================================
        # INSERT CURRENT VALUES
        # =====================================================

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
                cam.port
                or 554
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
        # POPUP STATUS
        # =====================================================

        current_status = getattr(
            cam,
            "status",
            1
        )

        is_popup_enabled = (
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
                if is_popup_enabled
                else "No"
            )
        )

        tk.Label(
            form,
            text="Pop up:",
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
            text="Yes",
            variable=status_var,
            value="Yes",
            bg="white"
        ).pack(
            side="left",
            padx=(0, 15)
        )

        tk.Radiobutton(
            radio_f,
            text="No",
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
    # SAVE CAMERA EDIT
    # =========================================================

    def save_camera_changes(
        self,
        cam,
        entries,
        status_var,
        window
    ):
        """
        Safely save camera edits.

        Important:
        We update the SAME Camera object.

        We do NOT reload all cameras from SQLite.

        This prevents MainPage and CentralPreview from holding
        stale references to old Camera objects.
        """

        # =====================================================
        # READ VALUES
        # =====================================================

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

            port = int(
                port_raw
            ) if port_raw else 554

            if not (
                1
                <= port
                <= 65535
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

                if hasattr(
                    camera_db,
                    "camera_exists"
                ):

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
            if status_var.get()
            == "Yes"
            else 0
        )

        # =====================================================
        # DETECT CHANGES
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

        # =====================================================
        # NOTHING CHANGED
        # =====================================================

        if not (
            connection_changed
            or metadata_changed
        ):

            window.destroy()

            return

        # =====================================================
        # SAVE DATABASE FIRST
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
        # STOP CAMERA IF CONNECTION CHANGED
        # =====================================================

        if connection_changed:

            try:

                if cam.running:

                    cam.stop()

            except Exception as e:

                print(
                    f"Warning stopping camera "
                    f"{cam.id}: {e}"
                )

        # =====================================================
        # UPDATE SAME CAMERA OBJECT
        # =====================================================

        cam.ip = ip

        cam.port = port

        cam.username = username

        cam.password = password

        cam.name = name

        cam.status = status

        # =====================================================
        # REBUILD RTSP URL
        # =====================================================

        try:

            cam._update_url()

        except Exception as e:

            print(
                "Failed to update camera URL:",
                e
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
        # RESTART CAMERA IF NECESSARY
        # =====================================================

        if connection_changed:

            if self.is_visible:

                try:

                    cam.start()

                except Exception as e:

                    print(
                        f"Failed to restart "
                        f"camera {cam.id}: {e}"
                    )

        # =====================================================
        # KEEP CONTROLLER LIST SYNCHRONIZED
        # =====================================================

        if hasattr(
            self.controller,
            "cameras"
        ):

            self.controller.cameras = (
                self.cameras
            )

        # =====================================================
        # CLOSE EDIT WINDOW
        # =====================================================

        try:

            window.grab_release()

        except Exception:

            pass

        window.destroy()

        # =====================================================
        # REFRESH OTHER VIEWS
        # =====================================================

        self._notify_camera_change()

    # =========================================================
    # NOTIFY OTHER PAGES
    # =========================================================

    def _notify_camera_change(
        self
    ):
        """
        Tell MainPage and CentralPreview that camera data
        changed.

        No Camera objects are recreated.
        """

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
        Kept for compatibility.

        This method no longer destroys all Camera objects.

        Existing Camera objects are updated in-place when possible.
        """

        try:

            fresh_cameras = (
                camera_db.load_all_cameras()
                or []
            )

        except Exception as e:

            print(
                "Failed to reload cameras:",
                e
            )

            return

        old_by_id = {
            cam.id: cam
            for cam in self.cameras
        }

        # =====================================================
        # UPDATE EXISTING OBJECTS
        # =====================================================

        for fresh in fresh_cameras:

            existing = old_by_id.get(
                fresh.id
            )

            if existing is None:

                self.cameras.append(
                    fresh
                )

                self.add_camera_card(
                    fresh
                )

                continue

            # Detect connection changes.

            connection_changed = (
                existing.ip != fresh.ip
                or existing.port != fresh.port
                or existing.username != (
                    fresh.username or ""
                )
                or existing.password != (
                    fresh.password or ""
                )
            )

            if connection_changed:

                try:

                    if existing.running:

                        existing.stop()

                except Exception:

                    pass

            # Update object.

            existing.ip = fresh.ip

            existing.port = fresh.port

            existing.username = (
                fresh.username
            )

            existing.password = (
                fresh.password
            )

            existing.name = fresh.name

            existing.status = fresh.status

            try:

                existing._update_url()

            except Exception:

                pass

            if connection_changed:

                if self.is_visible:

                    try:

                        existing.start()

                    except Exception:

                        pass

            card = self.camera_cards.get(
                existing.id
            )

            if card:

                try:

                    if hasattr(
                        card,
                        "update_info"
                    ):

                        card.update_info()

                except Exception:

                    pass

        # =====================================================
        # REMOVE DELETED CAMERAS
        # =====================================================

        fresh_ids = {
            cam.id
            for cam in fresh_cameras
        }

        for cam in list(
            self.cameras
        ):

            if cam.id not in fresh_ids:

                try:

                    if cam.running:

                        cam.stop()

                except Exception:

                    pass

                card = self.camera_cards.pop(
                    cam.id,
                    None
                )

                if card:

                    try:

                        card.destroy()

                    except Exception:

                        pass

                self.cameras.remove(
                    cam
                )

        # =====================================================
        # SYNC CONTROLLER
        # =====================================================

        if hasattr(
            self.controller,
            "cameras"
        ):

            self.controller.cameras = (
                self.cameras
            )

        self._notify_camera_change()

    # =========================================================
    # SIMPLE RELOAD
    # =========================================================

    def reload_cameras(
        self
    ):

        self._notify_camera_change()

    # =========================================================
    # DELETE CAMERA
    # =========================================================

    def _on_card_deleted(
        self,
        cam_id
    ):

        # =====================================================
        # FIND CAMERA
        # =====================================================

        cam = next(
            (
                c
                for c in self.cameras
                if c.id == cam_id
            ),
            None
        )

        # =====================================================
        # STOP CAMERA
        # =====================================================

        if cam:

            try:

                if cam.running:

                    cam.stop()

            except Exception as e:

                print(
                    f"Error stopping deleted "
                    f"camera {cam_id}: {e}"
                )

        # =====================================================
        # REMOVE CARD
        # =====================================================

        card = self.camera_cards.pop(
            cam_id,
            None
        )

        if card:

            try:

                card.destroy()

            except Exception:

                pass

        # =====================================================
        # REMOVE FROM LIST
        # =====================================================

        self.cameras = [
            camera
            for camera in self.cameras
            if camera.id != cam_id
        ]

        # =====================================================
        # CONTROLLER
        # =====================================================

        if hasattr(
            self.controller,
            "cameras"
        ):

            self.controller.cameras = (
                self.cameras
            )

        # =====================================================
        # UPDATE UI
        # =====================================================

        self.refresh_modbus_ui()

        self._notify_camera_change()

    # =========================================================
    # AUTO SEARCH
    # =========================================================

    def open_auto_search_window(
        self
    ):

        def on_camera_added(
            new_cam
        ):

            if new_cam is None:

                return

            # Avoid duplicates.

            if any(
                cam.id == new_cam.id
                for cam in self.cameras
            ):

                return

            self.cameras.append(
                new_cam
            )

            if hasattr(
                self.controller,
                "cameras"
            ):

                self.controller.cameras = (
                    self.cameras
                )

            self.add_camera_card(
                new_cam
            )

            if self.is_visible:

                try:

                    new_cam.start()

                except Exception as e:

                    print(
                        "Auto-search camera "
                        f"start error: {e}"
                    )

            self.refresh_modbus_ui()

            self._notify_camera_change()

        search = AutoSearchWindow(
            self,
            on_camera_added
        )

        search.show()

    # =========================================================
    # GET CAMERAS
    # =========================================================

    def get_cameras(
        self
    ):

        return list(
            self.cameras
        )

    # =========================================================
    # STOP ALL CAMERAS
    # =========================================================

    def stop_all_cameras(
        self
    ):

        for cam in list(
            self.cameras
        ):

            try:

                if cam.running:

                    cam.stop()

            except Exception as e:

                print(
                    f"Failed to stop camera "
                    f"{getattr(cam, 'id', 'unknown')}: "
                    f"{e}"
                )

    # =========================================================
    # SAVE SETTINGS
    # =========================================================

    def save_settings(
        self
    ):

        print(
            "Saved Settings:",
            self.screen_view.get(),
            self.language.get(),
            self.date_entry.get(),
            self.time_entry.get()
        )

    # =========================================================
    # REFRESH MODBUS UI
    # =========================================================

    def refresh_modbus_ui(
        self
    ):

        if hasattr(
            self,
            "zone_label"
        ):

            self.zone_label.configure(
                text=(
                    f"zone # "
                    f"{camera_db.get_next_modbus()}"
                )
            )

    # =========================================================
    # DESTROY
    # =========================================================

    def destroy(
        self
    ):
        """
        Clean up page-owned resources.
        """

        # =====================================================
        # REMOVE GLOBAL BINDING
        # =====================================================

        try:

            self.unbind_all(
                "<MouseWheel>"
            )

        except Exception:

            pass

        # =====================================================
        # STOP CAMERAS
        # =====================================================

        try:

            self.stop_all_cameras()

        except Exception:

            pass

        # =====================================================
        # STOP PLC
        # =====================================================

        if self.plc_reader:

            try:

                if hasattr(
                    self.plc_reader,
                    "stop"
                ):

                    self.plc_reader.stop()

            except Exception:

                pass

        super().destroy()