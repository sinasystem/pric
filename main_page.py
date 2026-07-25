import tkinter as tk
from tkinter import messagebox

from .constants import COLOR_BG
from .monitor_slot import MonitorSlot
import modules.camera_db as camera_db


print("Loaded main_page:", __file__)


class MainPage(tk.Frame):

    # =========================================================
    # CAMERA LAYOUT
    # =========================================================
    #
    # The camera composition is based on these ideal dimensions:
    #
    #                  BIG CAMERA
    #              16 units x 9 units
    #
    #       ┌───────────────────────┬──────┐
    #       │                       │      │
    #       │                       │ 4:9  │
    #       │       16:9            │      │
    #       │                       │      │
    #       └───────────────────────┴──────┘
    #
    # The small column contains four 16:9 cameras:
    #
    #       small width  = 4 units
    #       small height = 9 units
    #
    # Four cameras:
    #
    #       4 x 9 = 36 units high
    #
    # Therefore:
    #
    #       Big camera:
    #           16 x 9
    #
    #       Small column:
    #           4 x 36
    #
    # The entire composition is scaled uniformly.
    #
    # This is the important part:
    #
    #       scale = min(scale_x, scale_y)
    #
    # Every dimension is then multiplied by that same scale.
    #
    # This means resizing the application window will resize
    # ALL camera components proportionally.
    #
    # =========================================================

    # Base dimensions for the big camera.
    BASE_BIG_WIDTH = 16
    BASE_BIG_HEIGHT = 9

    # Base dimensions for one small camera.
    BASE_SMALL_WIDTH = 4
    BASE_SMALL_HEIGHT = 9

    # Number of small cameras.
    SMALL_SLOT_COUNT = 4

    # Base gap between big and small camera columns.
    BASE_BIG_SMALL_GAP = 1

    # Base gap between small cameras.
    BASE_SMALL_GAP = 0.25

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

        self.retry_after_id = None

        self.all_cameras = []

        self.refreshing = False

        # =====================================================
        # MONITOR SLOTS
        # =====================================================

        self.slots = []

        self.small_slots = []

        self.big_slot = None

        # =====================================================
        # MAIN PAGE GRID
        # =====================================================

        self.grid_rowconfigure(
            0,
            weight=0
        )

        self.grid_rowconfigure(
            1,
            weight=1
        )

        self.grid_columnconfigure(
            0,
            weight=1
        )

        self.grid_propagate(
            False
        )

        self.pack_propagate(
            False
        )

        # =====================================================
        # TOOLBAR
        # =====================================================

        self.create_toolbar()

        # =====================================================
        # CAMERA AREA
        # =====================================================

        self.grid_frame = tk.Frame(
            self,
            bg=COLOR_BG
        )

        self.grid_frame.grid(
            row=1,
            column=0,
            sticky="nsew",
            padx=20,
            pady=(10, 10)
        )

        self.grid_frame.grid_propagate(
            False
        )

        self.grid_frame.pack_propagate(
            False
        )

        # =====================================================
        # BUILD CAMERA LAYOUT
        # =====================================================

        self.build_monitor_grid()

        # =====================================================
        # RESPONSIVE RESIZE
        # =====================================================
        #
        # Every time grid_frame changes size, the entire camera
        # composition is recalculated.
        #
        # The same scale factor is applied to every component.
        #
        # =====================================================

        self.grid_frame.bind(
            "<Configure>",
            self._resize_camera_layout
        )

    # =========================================================
    # HELPER METHODS
    # =========================================================

    def _cancel_retry_timer(
        self
    ):
        """
        Safely cancel the current scheduled refresh.
        """

        if self.retry_after_id is None:
            return

        try:

            self.after_cancel(
                self.retry_after_id
            )

        except Exception:
            pass

        finally:

            self.retry_after_id = None

    # =========================================================

    def _is_cam_online(
        self,
        cam
    ):
        """
        Check whether the camera has successfully received
        frames from its RTSP stream.

        New Camera class API:

            cam.is_online()
        """

        if cam is None:
            return False

        try:

            return bool(
                cam.is_online()
            )

        except Exception as e:

            print(
                f"Failed to check camera status: {e}"
            )

            return False

    # =========================================================

    def _is_cam_running(
        self,
        cam
    ):
        """
        Check whether the Camera worker thread is running.

        New Camera class API:

            cam.running
        """

        if cam is None:
            return False

        try:

            return bool(
                cam.running
            )

        except Exception:

            return False

    # =========================================================

    def _get_cameras(
        self
    ):
        """
        Get cameras from the controller.

        Preferred:

            controller.cameras

        Fallback:

            DeviceManagerPage.get_cameras()
        """

        # =====================================================
        # CONTROLLER CAMERAS
        # =====================================================

        if hasattr(
            self.controller,
            "cameras"
        ):

            cameras = (
                self.controller.cameras
            )

            if cameras:

                return list(
                    cameras
                )

        # =====================================================
        # DEVICE MANAGER FALLBACK
        # =====================================================

        if (
            hasattr(
                self.controller,
                "frames"
            )
            and
            "DeviceManagerPage"
            in self.controller.frames
        ):

            device_page = (
                self.controller.frames[
                    "DeviceManagerPage"
                ]
            )

            if hasattr(
                device_page,
                "get_cameras"
            ):

                try:

                    return (
                        device_page.get_cameras()
                        or []
                    )

                except Exception as e:

                    print(
                        "Failed to get cameras "
                        f"from DeviceManagerPage: {e}"
                    )

        return []

    # =========================================================
    # PAGE LIFECYCLE
    # =========================================================

    def tkraise(
        self,
        *args,
        **kwargs
    ):
        """
        Called when this page becomes visible.
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
        Activate page and refresh camera assignments.
        """

        self.is_visible = True

        self.refresh_view()

        # Wait for Tkinter to finish calculating the actual
        # widget dimensions before resizing the layout.
        self.after(
            50,
            self._resize_camera_layout
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
        Hide camera views when leaving the page.

        Camera worker threads are NOT stopped.

        Camera objects are owned by the controller.
        """

        self.is_visible = False

        self._cancel_retry_timer()

        # =====================================================
        # CLEAR BIG PREVIEW
        # =====================================================

        if self.big_slot:

            self.big_slot.clear()

        # =====================================================
        # CLEAR SMALL PREVIEWS
        # =====================================================

        for slot in self.small_slots:

            slot.clear()

    # =========================================================
    # TOOLBAR
    # =========================================================

    def create_toolbar(
        self
    ):

        toolbar = tk.Frame(
            self,
            bg=COLOR_BG
        )

        toolbar.grid(
            row=0,
            column=0,
            sticky="ew",
            padx=20,
            pady=(10, 5)
        )

        toolbar.grid_columnconfigure(
            0,
            weight=1
        )

        toolbar.grid_columnconfigure(
            1,
            weight=1
        )

        # =====================================================
        # SETTINGS
        # =====================================================

        tk.Button(
            toolbar,
            text="⚙️ Settings",
            font=(
                "Arial",
                11,
                "bold"
            ),
            width=12,
            command=self.ask_password
        ).grid(
            row=0,
            column=0,
            sticky="w"
        )

        # =====================================================
        # MODE
        # =====================================================

        self.mode = tk.StringVar(
            value="AUTO"
        )

        mode_frame = tk.Frame(
            toolbar,
            bg=COLOR_BG
        )

        mode_frame.grid(
            row=0,
            column=1,
            sticky="e"
        )

        # =====================================================
        # AUTO MODE
        # =====================================================

        tk.Radiobutton(
            mode_frame,
            text="Auto",
            variable=self.mode,
            value="AUTO",
            command=self.refresh_view,
            bg=COLOR_BG,
            fg="white",
            selectcolor=COLOR_BG
        ).pack(
            side="left",
            padx=10
        )

        # =====================================================
        # HMI MODE
        # =====================================================

        tk.Radiobutton(
            mode_frame,
            text="HMI",
            variable=self.mode,
            value="HMI",
            command=self.refresh_view,
            bg=COLOR_BG,
            fg="white",
            selectcolor=COLOR_BG
        ).pack(
            side="left"
        )

    # =========================================================
    # BUILD MONITOR GRID
    # =========================================================

    def build_monitor_grid(
        self
    ):
        """
        Create the camera containers.

        The actual sizes are controlled by
        _resize_camera_layout().
        """

        # =====================================================
        # REMOVE OLD WIDGETS
        # =====================================================

        for widget in (
            self.grid_frame.winfo_children()
        ):

            widget.destroy()

        self.slots = []

        self.small_slots = []

        # =====================================================
        # BIG CAMERA CONTAINER
        # =====================================================

        self.left_frame = tk.Frame(
            self.grid_frame,
            bg=COLOR_BG
        )

        self.left_frame.place(
            x=0,
            y=0
        )

        self.left_frame.pack_propagate(
            False
        )

        self.left_frame.grid_propagate(
            False
        )

        # =====================================================
        # BIG CAMERA
        # =====================================================

        self.big_slot = MonitorSlot(
            self.left_frame
        )

        self.big_slot.pack(
            fill="both",
            expand=True
        )

        self.slots.append(
            self.big_slot
        )

        # =====================================================
        # SMALL CAMERA COLUMN
        # =====================================================

        self.right_frame = tk.Frame(
            self.grid_frame,
            bg=COLOR_BG
        )

        self.right_frame.place(
            x=0,
            y=0
        )

        self.right_frame.pack_propagate(
            False
        )

        self.right_frame.grid_propagate(
            False
        )

        # =====================================================
        # SMALL CAMERA SLOTS
        # =====================================================

        for index in range(
            self.SMALL_SLOT_COUNT
        ):

            slot_container = tk.Frame(
                self.right_frame,
                bg=COLOR_BG
            )

            slot_container.place(
                x=0,
                y=0
            )

            slot_container.pack_propagate(
                False
            )

            slot_container.grid_propagate(
                False
            )

            # -------------------------------------------------
            # MONITOR SLOT
            # -------------------------------------------------

            slot = MonitorSlot(
                slot_container
            )

            slot.pack(
                fill="both",
                expand=True
            )

            # -------------------------------------------------
            # CLICK CALLBACK
            # -------------------------------------------------
            #
            # Clicking this slot displays its camera in the
            # shared big preview.
            #
            # -------------------------------------------------

            slot.click_callback = (
                self.show_in_big_slot
            )

            self.small_slots.append(
                slot
            )

            self.slots.append(
                slot
            )

    # =========================================================
    # RESPONSIVE CAMERA LAYOUT
    # =========================================================

    def _resize_camera_layout(self, event=None):
        if not hasattr(self, "grid_frame"):
            return

        if not hasattr(self, "left_frame"):
            return

        if not hasattr(self, "right_frame"):
            return

        available_width = self.grid_frame.winfo_width()
        available_height = self.grid_frame.winfo_height()

        if available_width <= 1 or available_height <= 1:
            return

        # ---------------------------------------------------------
        # Layout configuration
        # ---------------------------------------------------------

        aspect_ratio = 16 / 9

        gap = max(
            4,
            int(min(available_width, available_height) * 0.01)
        )

        # The small camera height is limited by:
        #
        #   4 cameras
        #   + 3 gaps
        #
        max_small_height_by_height = (
            available_height - (3 * gap)
        ) / 4

        # ---------------------------------------------------------
        # Width constraint
        # ---------------------------------------------------------
        #
        # We want:
        #
        # big_width + gap + small_width <= available_width
        #
        # The big camera is larger than the small cameras.
        #
        # Use a ratio to control the size difference.
        #
        # Example:
        #
        # small camera = 1 unit
        # big camera   = 3 units
        #
        # ---------------------------------------------------------

        big_to_small_ratio = 3.0

        # Let:
        #
        # small_width = W
        # big_width   = W * 3
        #
        # Then:
        #
        # 3W + gap + W <= available_width
        #
        # 4W <= available_width - gap

        max_small_width_by_width = (
            available_width - gap
        ) / (
            big_to_small_ratio + 1
        )

        max_small_height_by_width = (
            max_small_width_by_width
            / aspect_ratio
        )

        # ---------------------------------------------------------
        # Choose the largest possible small camera size
        # ---------------------------------------------------------

        small_height = min(
            max_small_height_by_height,
            max_small_height_by_width
        )

        small_width = (
            small_height
            * aspect_ratio
        )

        # ---------------------------------------------------------
        # Big camera
        # ---------------------------------------------------------

        big_width = (
            small_width
            * big_to_small_ratio
        )

        big_height = (
            big_width
            / aspect_ratio
        )

        # ---------------------------------------------------------
        # Total dimensions
        # ---------------------------------------------------------

        total_width = (
            big_width
            + gap
            + small_width
        )

        total_height = max(
            big_height,
            (
                small_height * 4
                + gap * 3
            )
        )

        # ---------------------------------------------------------
        # Center layout
        # ---------------------------------------------------------

        start_x = (
            available_width
            - total_width
        ) / 2

        start_y = (
            available_height
            - total_height
        ) / 2

        # ---------------------------------------------------------
        # Big camera
        # ---------------------------------------------------------

        self.left_frame.place(
            x=int(start_x),
            y=int(start_y),
            width=int(big_width),
            height=int(big_height)
        )

        # ---------------------------------------------------------
        # Small camera column
        # ---------------------------------------------------------

        right_x = (
            start_x
            + big_width
            + gap
        )

        self.right_frame.place(
            x=int(right_x),
            y=int(start_y),
            width=int(small_width),
            height=int(total_height)
        )

        # ---------------------------------------------------------
        # Individual small cameras
        # ---------------------------------------------------------

        for index, slot in enumerate(
            self.small_slots
        ):

            slot_container = slot.master

            slot_y = (
                index
                * (
                    small_height
                    + gap
                )
            )

            slot_container.place(
                x=0,
                y=int(slot_y),
                width=int(small_width),
                height=int(small_height)
            )
    # =========================================================
    # CAMERA SELECTION
    # =========================================================

    def get_selected_cameras(
        self,
        cameras
    ):
        """
        Select cameras according to AUTO/HMI mode.
        """

        if not cameras:

            return []

        # =====================================================
        # AUTO MODE
        # =====================================================

        if self.mode.get() == "AUTO":

            return list(
                cameras
            )

        # =====================================================
        # HMI MODE
        # =====================================================

        try:

            if hasattr(
                self.controller,
                "get_active_zones"
            ):

                active_zones = (
                    self.controller
                    .get_active_zones()
                )

            else:

                active_zones = [1]

        except Exception:

            active_zones = [1]

        return [
            cam
            for cam in cameras
            if getattr(
                cam,
                "zone",
                None
            ) in active_zones
        ]

    # =========================================================
    # REFRESH CAMERA VIEW
    # =========================================================

    def refresh_view(
        self
    ):
        """
        Start cameras and assign them to the four small slots.

        The big slot is a shared preview and is independent
        of the four small slots.
        """

        if not self.is_visible:

            return

        if self.refreshing:

            return

        self.refreshing = True

        try:

            # =================================================
            # CANCEL OLD RETRY
            # =================================================

            self._cancel_retry_timer()

            # =================================================
            # GET CAMERAS
            # =================================================

            cameras = (
                self._get_cameras()
            )

            selected = (
                self.get_selected_cameras(
                    cameras
                )
            )

            self.all_cameras = (
                selected
            )

            # =================================================
            # NO CAMERAS
            # =================================================

            if not selected:

                self.clear_unused_slots(
                    0
                )

                return

            # =================================================
            # START CAMERA WORKERS
            # =================================================

            for cam in selected:

                try:

                    if not self._is_cam_running(
                        cam
                    ):

                        cam.start()

                except Exception as e:

                    print(
                        "Failed to start camera "
                        f"{getattr(cam, 'ip', 'Unknown')}: "
                        f"{e}"
                    )

            # =================================================
            # FIRST FOUR CAMERAS
            # =================================================

            visible_cameras = (
                selected[
                    :self.SMALL_SLOT_COUNT
                ]
            )

            # =================================================
            # ASSIGN SMALL SLOTS
            # =================================================

            for index, slot in enumerate(
                self.small_slots
            ):

                if index < len(
                    visible_cameras
                ):

                    camera = (
                        visible_cameras[
                            index
                        ]
                    )

                    # Don't repeatedly call set_camera()
                    # if the slot already displays this camera.

                    if slot.cam is not camera:

                        slot.set_camera(
                            camera
                        )

                else:

                    slot.clear()

            # =================================================
            # SHARED BIG PREVIEW
            # =================================================

            if self.big_slot:

                current_big_camera = (
                    self.big_slot.cam
                )

                # If the currently selected big camera
                # doesn't exist anymore, show the first
                # available small camera.

                if (
                    current_big_camera
                    not in visible_cameras
                ):

                    if visible_cameras:

                        self.big_slot.set_camera(
                            visible_cameras[0]
                        )

                    else:

                        self.big_slot.clear()

            # =================================================
            # CHECK CONNECTIONS
            # =================================================

            any_offline = any(
                not self._is_cam_online(
                    cam
                )
                for cam in visible_cameras
            )

            # =================================================
            # RETRY
            # =================================================

            if (
                any_offline
                and self.is_visible
            ):

                self.retry_after_id = (
                    self.after(
                        2000,
                        self.refresh_view
                    )
                )

        except Exception as e:

            print(
                "ERROR while refreshing camera view:",
                e
            )

        finally:

            self.refreshing = False

    # =========================================================
    # RELOAD CAMERAS
    # =========================================================

    def reload_cameras(
        self
    ):
        """
        Clear all slot assignments and refresh.
        """

        self._cancel_retry_timer()

        # =====================================================
        # BIG SLOT
        # =====================================================

        if self.big_slot:

            self.big_slot.clear()

        # =====================================================
        # SMALL SLOTS
        # =====================================================

        for slot in self.small_slots:

            slot.clear()

        self.all_cameras = []

        self.refreshing = False

        # =====================================================
        # REFRESH
        # =====================================================

        if self.is_visible:

            self.after(
                200,
                self.refresh_view
            )

    # =========================================================
    # CLEAR UNUSED SLOTS
    # =========================================================

    def clear_unused_slots(
        self,
        camera_count
    ):
        """
        Clear slots that don't have cameras.
        """

        # =====================================================
        # BIG SLOT
        # =====================================================

        if camera_count == 0:

            if self.big_slot:

                self.big_slot.clear()

        # =====================================================
        # SMALL SLOTS
        # =====================================================

        for index, slot in enumerate(
            self.small_slots
        ):

            if index >= camera_count:

                slot.clear()

    # =========================================================
    # SHOW CAMERA IN BIG SLOT
    # =========================================================

    def show_in_big_slot(
        self,
        cam
    ):
        """
        Show a camera from a small slot in the shared big slot.
        """

        if cam is None:

            return

        if not self.big_slot:

            return

        # Already showing this camera.
        if self.big_slot.cam is cam:

            return

        self.big_slot.set_camera(
            cam
        )

    # =========================================================
    # ADMIN LOGIN
    # =========================================================

    def ask_password(
        self
    ):

        password_window = tk.Toplevel(
            self
        )

        password_window.title(
            "Admin Login"
        )

        password_window.geometry(
            "340x240"
        )

        password_window.resizable(
            False,
            False
        )

        password_window.configure(
            bg="#2b2b2b"
        )

        # =====================================================
        # MODAL
        # =====================================================

        password_window.transient(
            self.winfo_toplevel()
        )

        password_window.grab_set()

        # =====================================================
        # TITLE
        # =====================================================

        tk.Label(
            password_window,
            text="Admin Login",
            font=(
                "Arial",
                15,
                "bold"
            ),
            bg="#2b2b2b",
            fg="white"
        ).pack(
            pady=(15, 5)
        )

        # =====================================================
        # DESCRIPTION
        # =====================================================

        tk.Label(
            password_window,
            text="Enter Password",
            font=(
                "Arial",
                10
            ),
            bg="#2b2b2b",
            fg="#dddddd"
        ).pack()

        # =====================================================
        # PASSWORD FRAME
        # =====================================================

        password_frame = tk.Frame(
            password_window,
            bg="#2b2b2b"
        )

        password_frame.pack(
            pady=15
        )

        # =====================================================
        # PASSWORD ENTRY
        # =====================================================

        password_entry = tk.Entry(
            password_frame,
            show="*",
            width=22,
            font=(
                "Arial",
                11
            ),
            bg="#3c3f41",
            fg="white",
            insertbackground="white",
            relief="flat"
        )

        password_entry.pack(
            side="left",
            ipady=4
        )

        # =====================================================
        # CHECK PASSWORD
        # =====================================================

        def check_password():

            if (
                password_entry.get()
                == camera_db.get_admin_password()
            ):

                password_window.destroy()

                self.on_hide()

                self.controller.show_frame(
                    "DeviceManagerPage"
                )

            else:

                messagebox.showerror(
                    "Error",
                    "Wrong Password",
                    parent=password_window
                )

        # =====================================================
        # ENTER KEY
        # =====================================================

        password_entry.bind(
            "<Return>",
            lambda event: check_password()
        )

        # =====================================================
        # LOGIN BUTTON
        # =====================================================

        tk.Button(
            password_window,
            text="LOGIN",
            font=(
                "Arial",
                10,
                "bold"
            ),
            bg="#00a86b",
            fg="white",
            relief="flat",
            width=18,
            command=check_password
        ).pack(
            pady=10
        )

        password_entry.focus_set()