# gui/camera_app.py

import sys
import threading
import tkinter as tk
from tkinter import messagebox

from .constants import COLOR_BG, FONT_FOOTER
from .main_page import MainPage
from .device_manager_page import DeviceManagerPage

import modules.camera_db as camera_db


class CameraApp(tk.Tk):
    """
    Main application controller.

    CameraApp is the SINGLE owner of:

        - Camera objects
        - Camera registry
        - Camera worker threads
        - Camera stream lifecycle

    GUI pages must NEVER directly call:

        cam.start()
        cam.stop()
        stop_all_cameras()

    GUI pages should instead use:

        controller.get_cameras()
        controller.start_camera(cam)
        controller.stop_camera(cam)
        controller.reload_cameras()

    Camera status:

        status = 1
            Camera is enabled and may run.

        status = 0
            Camera is disabled / under maintenance.
            Its stream MUST NOT run.

    Page switching never stops camera streams.

    Camera streams are stopped only when:

        1. A camera is explicitly disabled.
        2. A camera is deleted.
        3. A camera connection configuration is changed.
        4. The entire application is closed.
    """

    def __init__(self):

        # =========================================================
        # APPLICATION STATE
        # =========================================================

        self.closing = False

        # ---------------------------------------------------------
        # SHARED CAMERA REGISTRY
        # ---------------------------------------------------------
        #
        # This is the SINGLE source of truth for Camera objects.
        #
        # MainPage and DeviceManagerPage must use these objects.
        #
        self.cameras = []

        # ---------------------------------------------------------
        # ACTIVE STREAM REGISTRY
        # ---------------------------------------------------------
        #
        # camera_id -> Camera object
        #
        # Only cameras that CameraApp has started should appear
        # here.
        #
        self.camera_streams = {}

        # ---------------------------------------------------------
        # THREAD SAFETY
        # ---------------------------------------------------------

        self.camera_lock = threading.RLock()

        # =========================================================
        # TK INITIALIZATION
        # =========================================================

        super().__init__()

        self.title(
            "GORIZ Camera System"
        )

        try:

            self.state(
                "zoomed"
            )

        except tk.TclError:

            self.geometry(
                f"{self.winfo_screenwidth()}x"
                f"{self.winfo_screenheight()}"
            )

        self.minsize(
            1200,
            700
        )

        self.configure(
            bg=COLOR_BG
        )

        self.grid_rowconfigure(
            1,
            weight=1
        )

        self.grid_columnconfigure(
            0,
            weight=1
        )

        self.protocol(
            "WM_DELETE_WINDOW",
            self.close_app
        )

        # =========================================================
        # LOAD CAMERAS
        # =========================================================

        self._load_cameras()

        # =========================================================
        # HEADER
        # =========================================================

        self.create_header()

        # =========================================================
        # PAGE CONTAINER
        # =========================================================

        container = tk.Frame(
            self,
            bg=COLOR_BG
        )

        container.grid(
            row=1,
            column=0,
            sticky="nsew"
        )

        container.grid_rowconfigure(
            0,
            weight=1
        )

        container.grid_columnconfigure(
            0,
            weight=1
        )

        # =========================================================
        # CREATE PAGES
        # =========================================================

        self.frames = {}

        self.current_frame = None

        for Page in (
            MainPage,
            DeviceManagerPage
        ):

            page_name = Page.__name__

            frame = Page(
                container,
                self
            )

            self.frames[
                page_name
            ] = frame

            frame.grid(
                row=0,
                column=0,
                sticky="nsew"
            )

        # =========================================================
        # SHOW INITIAL PAGE
        # =========================================================

        self.show_frame(
            "MainPage"
        )

        # =========================================================
        # FOOTER
        # =========================================================

        footer = tk.Label(
            self,
            text=(
                "License by Goriz Security Electric Fence System     "
                "www.goriz.org"
            ),
            font=FONT_FOOTER,
            bg=COLOR_BG,
            fg="white"
        )

        footer.grid(
            row=2,
            column=0,
            pady=10
        )

    # =============================================================
    # CAMERA REGISTRY
    # =============================================================

    def _load_cameras(self):
        """
        Load all cameras from the database.

        This is called once during application startup.

        Only CameraApp creates the initial Camera objects.

        Pages receive references to these same objects.
        """

        try:

            cameras = (
                camera_db.load_all_cameras()
                or []
            )

            with self.camera_lock:

                self.cameras = list(
                    cameras
                )

            print(
                f"[CameraApp] Loaded "
                f"{len(self.cameras)} camera(s)"
            )

        except Exception as e:

            print(
                "[CameraApp] Failed to load cameras:",
                e
            )

            self.cameras = []

    def get_cameras(self):
        """
        Return a copy of the shared Camera registry.

        The Camera objects themselves are NOT copied.

        Every caller receives references to the same Camera
        instances owned by CameraApp.
        """

        with self.camera_lock:

            return list(
                self.cameras
            )

    def get_camera(
        self,
        camera_id
    ):
        """
        Return a shared Camera object by database ID.
        """

        with self.camera_lock:

            for camera in self.cameras:

                if camera.id == camera_id:

                    return camera

        return None

    # =============================================================
    # CAMERA REGISTRATION
    # =============================================================

    def register_camera(
        self,
        camera
    ):
        """
        Register a newly created Camera object.

        Returns the existing shared object if the camera ID
        is already registered.
        """

        if camera is None:

            return None

        with self.camera_lock:

            existing = None

            for cam in self.cameras:

                if cam.id == camera.id:

                    existing = cam

                    break

            if existing is not None:

                return existing

            self.cameras.append(
                camera
            )

        print(
            f"[CameraApp] Registered camera "
            f"{camera.id}"
        )

        return camera

    def unregister_camera(
        self,
        camera_id
    ):
        """
        Permanently remove a camera.

        The shared stream is stopped first.

        This should only be used when a camera is deleted.
        """

        camera = self.get_camera(
            camera_id
        )

        if camera is None:

            return

        # ---------------------------------------------------------
        # STOP SHARED STREAM
        # ---------------------------------------------------------

        self.stop_camera(
            camera
        )

        # ---------------------------------------------------------
        # REMOVE FROM REGISTRY
        # ---------------------------------------------------------

        with self.camera_lock:

            self.cameras = [
                cam
                for cam in self.cameras
                if cam.id != camera_id
            ]

        print(
            f"[CameraApp] Unregistered camera "
            f"{camera_id}"
        )

    # =============================================================
    # CAMERA STATUS
    # =============================================================

    @staticmethod
    def is_camera_enabled(
        camera
    ):
        """
        Return True if the camera is enabled.

        status may come from SQLite as:

            0 / 1
            False / True
            "0" / "1"
            "false" / "true"
            "no" / "yes"
        """

        if camera is None:

            return False

        status = getattr(
            camera,
            "status",
            0
        )

        if isinstance(
            status,
            bool
        ):

            return status

        if isinstance(
            status,
            str
        ):

            return status.lower().strip() in (
                "1",
                "true",
                "yes",
                "on",
                "enabled"
            )

        try:

            return bool(
                int(status)
            )

        except (
            TypeError,
            ValueError
        ):

            return False

    # =============================================================
    # CAMERA STREAM MANAGEMENT
    # =============================================================

    def start_camera(
        self,
        camera
    ):
        """
        Start a shared camera stream.

        IMPORTANT:

        A camera with status OFF is NEVER started.

        Repeated calls are safe.
        """

        if camera is None:

            return False

        if self.closing:

            return False

        # ---------------------------------------------------------
        # STATUS CHECK
        # ---------------------------------------------------------
        #
        # Maintenance cameras must not consume resources.
        #
        if not self.is_camera_enabled(
            camera
        ):

            print(
                f"[CameraApp] Camera "
                f"{getattr(camera, 'id', '?')} "
                f"is disabled. Stream will not start."
            )

            # Defensive cleanup in case something previously
            # started this camera.
            self.stop_camera(
                camera
            )

            return False

        camera_id = getattr(
            camera,
            "id",
            None
        )

        try:

            with self.camera_lock:

                # -------------------------------------------------
                # Already tracked
                # -------------------------------------------------

                if camera_id in self.camera_streams:

                    if getattr(
                        camera,
                        "running",
                        False
                    ):

                        return True

                # -------------------------------------------------
                # Defensive status check again
                # -------------------------------------------------

                if not self.is_camera_enabled(
                    camera
                ):

                    return False

                # -------------------------------------------------
                # Start Camera worker
                # -------------------------------------------------

                if hasattr(
                    camera,
                    "start"
                ):

                    camera.start()

                # -------------------------------------------------
                # Track active stream
                # -------------------------------------------------

                self.camera_streams[
                    camera_id
                ] = camera

            print(
                f"[CameraApp] Started camera "
                f"{camera_id}"
            )

            return True

        except Exception as e:

            print(
                f"[CameraApp] Failed to start camera "
                f"{camera_id}: {e}"
            )

            return False

    def stop_camera(
        self,
        camera
    ):
        """
        Stop one shared camera stream.

        GUI pages should call this method instead of calling
        Camera.stop() directly.
        """

        if camera is None:

            return

        camera_id = getattr(
            camera,
            "id",
            None
        )

        try:

            if hasattr(
                camera,
                "stop"
            ):

                camera.stop()

        except Exception as e:

            print(
                f"[CameraApp] Error stopping camera "
                f"{camera_id}: {e}"
            )

        finally:

            with self.camera_lock:

                self.camera_streams.pop(
                    camera_id,
                    None
                )

    def start_enabled_cameras(
        self
    ):
        """
        Start all cameras whose status is enabled.

        Cameras with status OFF are explicitly stopped.
        """

        cameras = self.get_cameras()

        for camera in cameras:

            if self.is_camera_enabled(
                camera
            ):

                self.start_camera(
                    camera
                )

            else:

                self.stop_camera(
                    camera
                )

    def start_all_cameras(
        self
    ):
        """
        Compatibility wrapper.

        Despite the name, this does NOT start disabled cameras.

        Only cameras with status ON are started.
        """

        self.start_enabled_cameras()

    def stop_all_cameras(
        self
    ):
        """
        Stop every currently active shared camera stream.

        This should normally only be used during application
        shutdown or an explicit global stop operation.
        """

        with self.camera_lock:

            cameras = list(
                self.camera_streams.values()
            )

        for camera in cameras:

            self.stop_camera(
                camera
            )

        with self.camera_lock:

            self.camera_streams.clear()

        print(
            "[CameraApp] All camera streams stopped"
        )

    # =============================================================
    # UPDATE CAMERA STATUS
    # =============================================================

    def set_camera_status(
        self,
        camera,
        enabled
    ):
        """
        Change the runtime status of a camera.

        enabled = False
            Immediately stop the camera.

        enabled = True
            Start the camera.

        This method should be used by DeviceManagerPage instead
        of directly calling cam.start() / cam.stop().
        """

        if camera is None:

            return False

        status = (
            1
            if enabled
            else 0
        )

        # ---------------------------------------------------------
        # Update Camera object
        # ---------------------------------------------------------

        camera.status = status

        # ---------------------------------------------------------
        # Disabled
        # ---------------------------------------------------------

        if not enabled:

            self.stop_camera(
                camera
            )

            print(
                f"[CameraApp] Camera "
                f"{camera.id} disabled. "
                f"Stream stopped."
            )

            return False

        # ---------------------------------------------------------
        # Enabled
        # ---------------------------------------------------------

        print(
            f"[CameraApp] Camera "
            f"{camera.id} enabled."
        )

        return self.start_camera(
            camera
        )

    # =============================================================
    # CAMERA CONFIGURATION UPDATE
    # =============================================================

    def update_camera_configuration(
        self,
        camera,
        *,
        ip=None,
        port=None,
        username=None,
        password=None,
        name=None,
        status=None,
        zone=None
    ):
        """
        Update a shared Camera object in-place.

        The same Camera object remains shared between all pages.

        Connection changes:

            1. Stop current stream.
            2. Update configuration.
            3. Rebuild RTSP URL.
            4. Restart only if status is enabled.

        Status OFF:

            Stream remains stopped.

        Returns True on success.
        """

        if camera is None:

            return False

        # ---------------------------------------------------------
        # Determine new values
        # ---------------------------------------------------------

        new_ip = (
            camera.ip
            if ip is None
            else ip
        )

        new_port = (
            camera.port
            if port is None
            else port
        )

        new_username = (
            camera.username
            if username is None
            else username
        )

        new_password = (
            camera.password
            if password is None
            else password
        )

        new_name = (
            camera.name
            if name is None
            else name
        )

        new_status = (
            camera.status
            if status is None
            else status
        )

        new_zone = (
            camera.zone
            if zone is None
            else zone
        )

        # Normalize status.

        if isinstance(
            new_status,
            str
        ):

            new_status = (
                1
                if new_status.lower().strip()
                in (
                    "1",
                    "true",
                    "yes",
                    "on",
                    "enabled"
                )
                else 0
            )

        else:

            new_status = (
                1
                if bool(new_status)
                else 0
            )

        # ---------------------------------------------------------
        # Detect connection changes
        # ---------------------------------------------------------

        connection_changed = (
            new_ip
            != camera.ip
            or new_port
            != camera.port
            or new_username
            != (
                camera.username
                or ""
            )
            or new_password
            != (
                camera.password
                or ""
            )
        )

        old_status = (
            self.is_camera_enabled(
                camera
            )
        )

        new_status_enabled = (
            bool(new_status)
        )

        # ---------------------------------------------------------
        # Stop before changing connection information
        # ---------------------------------------------------------

        if connection_changed:

            self.stop_camera(
                camera
            )

        # ---------------------------------------------------------
        # Update SAME Camera object
        # ---------------------------------------------------------

        camera.ip = new_ip
        camera.port = new_port
        camera.username = new_username
        camera.password = new_password
        camera.name = new_name
        camera.status = new_status
        camera.zone = new_zone

        # ---------------------------------------------------------
        # Rebuild RTSP URL
        # ---------------------------------------------------------

        try:

            if hasattr(
                camera,
                "_update_url"
            ):

                camera._update_url()

        except Exception as e:

            print(
                "[CameraApp] Failed to rebuild "
                f"camera URL: {e}"
            )

        # ---------------------------------------------------------
        # Status OFF
        # ---------------------------------------------------------

        if not new_status_enabled:

            self.stop_camera(
                camera
            )

            return True

        # ---------------------------------------------------------
        # Connection changed or camera was previously OFF
        # ---------------------------------------------------------

        if (
            connection_changed
            or not old_status
        ):

            self.start_camera(
                camera
            )

        return True

    # =============================================================
    # CAMERA RELOAD
    # =============================================================

    def reload_cameras(
        self
    ):
        """
        Synchronize the camera registry with the database.

        Existing Camera objects are preserved whenever possible.

        This is critical because GUI pages may hold references
        to the shared Camera objects.

        Cameras that disappear from the database are stopped and
        removed from the registry.

        Cameras with status OFF are always stopped.

        Cameras with status ON that were previously running remain
        running.

        Newly enabled cameras may be started.
        """

        try:

            fresh_cameras = (
                camera_db.load_all_cameras()
                or []
            )

            # -----------------------------------------------------
            # Snapshot old registry
            # -----------------------------------------------------

            with self.camera_lock:

                old_cameras = list(
                    self.cameras
                )

                old_by_id = {
                    camera.id: camera
                    for camera in old_cameras
                }

                active_streams = dict(
                    self.camera_streams
                )

            # -----------------------------------------------------
            # Build new shared registry
            # -----------------------------------------------------

            new_cameras = []

            for fresh in fresh_cameras:

                existing = old_by_id.get(
                    fresh.id
                )

                # =================================================
                # NEW CAMERA
                # =================================================

                if existing is None:

                    new_cameras.append(
                        fresh
                    )

                    continue

                # =================================================
                # EXISTING CAMERA
                # =================================================

                connection_changed = (
                    existing.ip
                    != fresh.ip
                    or existing.port
                    != fresh.port
                    or existing.username
                    != (
                        fresh.username
                        or ""
                    )
                    or existing.password
                    != (
                        fresh.password
                        or ""
                    )
                )

                # -------------------------------------------------
                # If connection changed, stop BEFORE updating URL.
                # -------------------------------------------------

                if connection_changed:

                    self.stop_camera(
                        existing
                    )

                # -------------------------------------------------
                # Update same object
                # -------------------------------------------------

                existing.modbus = (
                    fresh.modbus
                )

                existing.zone = (
                    fresh.zone
                )

                existing.ip = (
                    fresh.ip
                )

                existing.port = (
                    fresh.port
                )

                existing.username = (
                    fresh.username
                )

                existing.password = (
                    fresh.password
                )

                existing.status = (
                    fresh.status
                )

                existing.name = (
                    fresh.name
                )

                # -------------------------------------------------
                # Rebuild URL
                # -------------------------------------------------

                try:

                    if hasattr(
                        existing,
                        "_update_url"
                    ):

                        existing._update_url()

                except Exception as e:

                    print(
                        "[CameraApp] Failed to update "
                        f"camera URL: {e}"
                    )

                new_cameras.append(
                    existing
                )

            # -----------------------------------------------------
            # Detect deleted cameras
            # -----------------------------------------------------

            new_ids = {
                camera.id
                for camera in new_cameras
            }

            old_ids = {
                camera.id
                for camera in old_cameras
            }

            removed_ids = (
                old_ids
                - new_ids
            )

            # -----------------------------------------------------
            # Stop deleted cameras
            # -----------------------------------------------------

            for camera_id in removed_ids:

                old_camera = (
                    old_by_id.get(
                        camera_id
                    )
                )

                if old_camera is not None:

                    print(
                        f"[CameraApp] Stopping "
                        f"removed camera {camera_id}"
                    )

                    self.stop_camera(
                        old_camera
                    )

            # -----------------------------------------------------
            # Replace registry
            # -----------------------------------------------------

            with self.camera_lock:

                self.cameras = (
                    new_cameras
                )

            # -----------------------------------------------------
            # Enforce status
            # -----------------------------------------------------
            #
            # This is important:
            #
            # If a camera was changed to status OFF in the DB,
            # its stream must be stopped.
            #
            # If it is ON, we leave its existing stream state
            # alone unless it was newly added.
            #
            for camera in new_cameras:

                if not self.is_camera_enabled(
                    camera
                ):

                    self.stop_camera(
                        camera
                    )

            # -----------------------------------------------------
            # Start newly enabled cameras
            # -----------------------------------------------------
            #
            # Only cameras that were not previously active are
            # started here.
            #
            for camera in new_cameras:

                if not self.is_camera_enabled(
                    camera
                ):

                    continue

                if camera.id not in active_streams:

                    # Do not automatically start every camera
                    # unless the application wants all enabled
                    # cameras active.
                    #
                    # MainPage can explicitly request streams.
                    continue

            print(
                f"[CameraApp] Reloaded "
                f"{len(new_cameras)} camera(s)"
            )

            return self.get_cameras()

        except Exception as e:

            print(
                "[CameraApp] Failed to reload cameras:",
                e
            )

            return self.get_cameras()

    # =============================================================
    # HEADER
    # =============================================================

    def create_header(
        self
    ):

        from .widgets import create_header

        create_header(
            self,
            self.close_app
        )

    # =============================================================
    # PAGE NAVIGATION
    # =============================================================

    def show_frame(
        self,
        page_name
    ):
        """
        Switch between GUI pages.

        IMPORTANT:

        Switching pages NEVER stops camera streams.

        CameraApp remains the owner of all active streams.
        """

        if self.closing:

            return

        target_frame = (
            self.frames.get(
                page_name
            )
        )

        if target_frame is None:

            print(
                f"[CameraApp] Unknown page: "
                f"{page_name}"
            )

            return

        # ---------------------------------------------------------
        # Hide current page
        # ---------------------------------------------------------

        if (
            self.current_frame is not None
            and self.current_frame
            != target_frame
        ):

            if hasattr(
                self.current_frame,
                "on_hide"
            ):

                try:

                    self.current_frame.on_hide()

                except Exception as e:

                    print(
                        "[CameraApp] Page hide error:",
                        e
                    )

        # ---------------------------------------------------------
        # Switch page
        # ---------------------------------------------------------

        self.current_frame = (
            target_frame
        )

        target_frame.tkraise()

        # ---------------------------------------------------------
        # Show target page
        # ---------------------------------------------------------

        if hasattr(
            target_frame,
            "on_show"
        ):

            try:

                target_frame.on_show()

            except Exception as e:

                print(
                    "[CameraApp] Page show error:",
                    e
                )

    # =============================================================
    # SCREEN VIEW
    # =============================================================

    def change_screen_view(
        self,
        view_count
    ):
        """
        Change the MainPage camera grid layout.
        """

        main_page = (
            self.frames.get(
                "MainPage"
            )
        )

        if main_page is None:

            return

        try:

            if hasattr(
                main_page,
                "build_monitor_grid"
            ):

                main_page.build_monitor_grid(
                    view_count
                )

            if hasattr(
                main_page,
                "refresh_view"
            ):

                main_page.refresh_view()

        except Exception as e:

            print(
                "[CameraApp] Failed to change "
                f"screen view: {e}"
            )

    # =============================================================
    # APPLICATION SHUTDOWN
    # =============================================================

    def close_app(
        self
    ):
        """
        Shut down the entire application.

        This is the ONLY normal place where all camera streams
        are stopped globally.
        """

        if self.closing:

            return

        if not messagebox.askokcancel(
            "Exit",
            "Are you sure you want to exit?"
        ):

            return

        self.closing = True

        print(
            "[CameraApp] Shutting down..."
        )

        # =========================================================
        # STOP ALL SHARED CAMERA STREAMS
        # =========================================================

        try:

            self.stop_all_cameras()

        except Exception as e:

            print(
                "[CameraApp] Camera shutdown error:",
                e
            )

        # =========================================================
        # PAGE CLEANUP
        # =========================================================
        #
        # IMPORTANT:
        #
        # We do NOT call stop_all_cameras() on pages.
        #
        # Pages may clean up:
        #
        #   - PLC readers
        #   - timers
        #   - preview widgets
        #   - GUI-only resources
        #
        # But they must not stop shared camera workers.
        #
        for frame in self.frames.values():

            if hasattr(
                frame,
                "on_hide"
            ):

                try:

                    frame.on_hide()

                except Exception as e:

                    print(
                        "[CameraApp] Page cleanup error:",
                        e
                    )

        # =========================================================
        # DATABASE
        # =========================================================

        try:

            camera_db.close()

        except Exception as e:

            print(
                "[CameraApp] Database close error:",
                e
            )

        # =========================================================
        # TK SHUTDOWN
        # =========================================================

        try:

            self.quit()

        except Exception:
            pass

        try:

            self.destroy()

        except Exception:
            pass

        sys.exit(0)
    def reconcile_camera_stream(self, camera, connection_changed=False):
        if camera is None:
            return

        # OFF = stream must not run
        if not getattr(camera, "status", False):
            self.stop_camera(camera)
            return

        # Connection changed while enabled
        if connection_changed:
            self.stop_camera(camera)

        # ON = stream should run
        self.start_camera(camera)