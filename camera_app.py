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
        - Camera worker lifecycle
        - Camera stream start/stop decisions

    GUI pages must NEVER directly call:

        cam.start()
        cam.stop()
        stop_all_cameras()

    GUI pages should use:

        controller.get_cameras()
        controller.get_camera(camera_id)
        controller.start_camera(camera)
        controller.stop_camera(camera)
        controller.set_camera_status(camera, enabled)
        controller.update_camera_configuration(...)
        controller.reload_cameras()

    Camera status:

        status = ON
            Camera is enabled and may run.

        status = OFF
            Camera is disabled / under maintenance.
            Its stream MUST NOT run.

    Page switching NEVER stops camera streams.

    Streams are stopped only when:

        1. Camera is explicitly disabled.
        2. Camera is deleted.
        3. Camera connection configuration changes.
        4. Application is closed.
    """

    # =============================================================
    # INITIALIZATION
    # =============================================================

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
        # Every page receives references to these SAME objects.
        #
        self.cameras = []

        # ---------------------------------------------------------
        # ACTIVE STREAM REGISTRY
        # ---------------------------------------------------------
        #
        # camera_id -> Camera object
        #
        # Only cameras whose streams are currently managed as
        # running by CameraApp should be stored here.
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
        # LOAD SHARED CAMERAS
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

        CameraApp creates the initial Camera objects.

        GUI pages must use these shared objects instead of loading
        their own Camera instances.
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
        Return a copy of the camera registry.

        The list is copied.

        The Camera objects themselves are NOT copied.

        Every caller receives references to the same shared
        Camera instances.
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

        The Camera object becomes owned by CameraApp.

        If the camera is disabled, its stream is NOT started.
        """

        if camera is None:

            return None

        with self.camera_lock:

            # -----------------------------------------------------
            # Prevent duplicate objects.
            # -----------------------------------------------------

            for existing in self.cameras:

                if existing.id == camera.id:

                    return existing

            self.cameras.append(
                camera
            )

        print(
            f"[CameraApp] Registered camera "
            f"{camera.id}"
        )

        # ---------------------------------------------------------
        # Enforce status.
        # ---------------------------------------------------------

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

        return camera

    def unregister_camera(
        self,
        camera_id
    ):
        """
        Permanently remove a camera.

        The stream is stopped first.

        This should only be called when a camera is deleted.
        """

        camera = self.get_camera(
            camera_id
        )

        if camera is None:

            return

        # ---------------------------------------------------------
        # Stop shared stream.
        # ---------------------------------------------------------

        self.stop_camera(
            camera
        )

        # ---------------------------------------------------------
        # Remove from registry.
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
        Return True when the camera status means ON.

        Supported values:

            1
            0
            True
            False
            "1"
            "0"
            "true"
            "false"
            "yes"
            "no"
            "on"
            "off"
            "enabled"
            "disabled"
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

            normalized = (
                status
                .strip()
                .lower()
            )

            if normalized in (
                "1",
                "true",
                "yes",
                "on",
                "enabled"
            ):

                return True

            if normalized in (
                "0",
                "false",
                "no",
                "off",
                "disabled",
                "",
                "none"
            ):

                return False

            return False

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
        Start one shared camera stream.

        A camera with status OFF is NEVER started.

        Returns:

            True
                Stream is running or was successfully started.

            False
                Camera was disabled or failed to start.
        """

        if camera is None:

            return False

        if self.closing:

            return False

        camera_id = getattr(
            camera,
            "id",
            None
        )

        # ---------------------------------------------------------
        # STATUS CHECK
        # ---------------------------------------------------------
        #
        # This is the most important rule:
        #
        # OFF cameras must never consume RTSP/OpenCV resources.
        #

        if not self.is_camera_enabled(
            camera
        ):

            # Defensive cleanup.
            #
            # If another part of the program somehow started
            # this camera, force it back into the correct state.
            self.stop_camera(
                camera
            )

            return False

        try:

            with self.camera_lock:

                # -------------------------------------------------
                # Already tracked.
                # -------------------------------------------------

                tracked_camera = (
                    self.camera_streams.get(
                        camera_id
                    )
                )

                if tracked_camera is camera:

                    # Stream is already managed.
                    if getattr(
                        camera,
                        "running",
                        False
                    ):

                        return True

                # -------------------------------------------------
                # Camera is not tracked or stopped unexpectedly.
                # -------------------------------------------------

                if hasattr(
                    camera,
                    "start"
                ):

                    camera.start()

                # -------------------------------------------------
                # Track active stream.
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

            with self.camera_lock:

                self.camera_streams.pop(
                    camera_id,
                    None
                )

            return False

    def stop_camera(
        self,
        camera
    ):
        """
        Stop one shared camera stream.

        GUI pages must NOT call Camera.stop() directly.

        This method is safe to call even if the camera is not
        currently running.
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
        Start all enabled cameras.

        Disabled cameras are explicitly stopped.

        This is useful after application initialization or after
        a configuration reload.
        """

        for camera in self.get_cameras():

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

        Despite the method name, disabled cameras are NEVER
        started.

        Only cameras with status ON are started.
        """

        self.start_enabled_cameras()

    def stop_all_cameras(
        self
    ):
        """
        Stop every currently active camera stream.

        Normally used only during application shutdown or an
        explicit global stop operation.

        Page switching must NOT call this method.
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
    # CAMERA STATUS UPDATE
    # =============================================================

    def set_camera_status(
        self,
        camera,
        enabled
    ):
        """
        Change the runtime status of a camera.

        enabled=False:

            Camera is immediately stopped.

        enabled=True:

            Camera is allowed to run and is started.

        DeviceManagerPage should use this method when the user
        enables or disables a camera.
        """

        if camera is None:

            return False

        new_status = (
            1
            if enabled
            else 0
        )

        # ---------------------------------------------------------
        # Update shared Camera object.
        # ---------------------------------------------------------

        camera.status = new_status

        # ---------------------------------------------------------
        # OFF
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
        # ON
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

        The same Camera object is preserved.

        Connection changes:

            1. Stop current stream.
            2. Update connection information.
            3. Rebuild RTSP URL.
            4. Restart if status is ON.

        Status OFF:

            Stream is always stopped.

        Non-connection changes such as name or zone do NOT restart
        the camera unnecessarily.
        """

        if camera is None:

            return False

        # =========================================================
        # DETERMINE NEW VALUES
        # =========================================================

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

        # =========================================================
        # NORMALIZE STATUS
        # =========================================================

        if isinstance(
            new_status,
            str
        ):

            new_status_enabled = (
                new_status
                .strip()
                .lower()
                in (
                    "1",
                    "true",
                    "yes",
                    "on",
                    "enabled"
                )
            )

            new_status = (
                1
                if new_status_enabled
                else 0
            )

        else:

            new_status = (
                1
                if bool(new_status)
                else 0
            )

            new_status_enabled = (
                bool(new_status)
            )

        # =========================================================
        # DETECT CONNECTION CHANGES
        # =========================================================

        connection_changed = (
            new_ip != camera.ip
            or new_port != camera.port
            or (
                new_username
                != (
                    camera.username
                    or ""
                )
            )
            or (
                new_password
                != (
                    camera.password
                    or ""
                )
            )
        )

        old_status_enabled = (
            self.is_camera_enabled(
                camera
            )
        )

        # =========================================================
        # STOP BEFORE CONNECTION CHANGE
        # =========================================================

        if connection_changed:

            self.stop_camera(
                camera
            )

        # =========================================================
        # UPDATE SAME SHARED OBJECT
        # =========================================================

        camera.ip = new_ip
        camera.port = new_port
        camera.username = new_username
        camera.password = new_password
        camera.name = new_name
        camera.status = new_status
        camera.zone = new_zone

        # =========================================================
        # REBUILD RTSP URL
        # =========================================================

        if connection_changed:

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

        # =========================================================
        # STATUS OFF
        # =========================================================

        if not new_status_enabled:

            self.stop_camera(
                camera
            )

            return True

        # =========================================================
        # CONNECTION CHANGED
        # =========================================================

        if connection_changed:

            self.start_camera(
                camera
            )

            return True

        # =========================================================
        # CAMERA WAS PREVIOUSLY OFF
        # =========================================================

        if not old_status_enabled:

            self.start_camera(
                camera
            )

            return True

        # =========================================================
        # CAMERA WAS ALREADY RUNNING/ENABLED
        # =========================================================

        # No restart required.
        #
        # Name / zone / other metadata changes are already applied
        # to the shared object.

        return True

    # =============================================================
    # CAMERA DATABASE RELOAD
    # =============================================================

    def reload_cameras(
        self
    ):
        """
        Synchronize CameraApp's shared camera registry with the DB.

        Existing Camera objects are preserved whenever possible.

        This is critical because GUI pages may hold references to
        the shared Camera objects.

        Behavior:

            Existing camera:
                Same object is updated in-place.

            Deleted camera:
                Stream is stopped and object is removed.

            Status OFF:
                Stream is stopped.

            Status ON:
                Existing running stream is preserved.

            Newly added enabled camera:
                Stream is started.

            Connection changed:
                Existing stream is stopped before URL/config update,
                then restarted if enabled.
        """

        try:

            fresh_cameras = (
                camera_db.load_all_cameras()
                or []
            )

            # =====================================================
            # SNAPSHOT OLD REGISTRY
            # =====================================================

            with self.camera_lock:

                old_cameras = list(
                    self.cameras
                )

                old_by_id = {
                    camera.id: camera
                    for camera in old_cameras
                }

            # =====================================================
            # BUILD NEW REGISTRY
            # =====================================================

            new_cameras = []

            for fresh in fresh_cameras:

                existing = (
                    old_by_id.get(
                        fresh.id
                    )
                )

                # -------------------------------------------------
                # NEW CAMERA
                # -------------------------------------------------

                if existing is None:

                    new_cameras.append(
                        fresh
                    )

                    continue

                # -------------------------------------------------
                # DETECT CONNECTION CHANGE
                # -------------------------------------------------

                connection_changed = (
                    existing.ip
                    != fresh.ip
                    or existing.port
                    != fresh.port
                    or (
                        existing.username
                        != (
                            fresh.username
                            or ""
                        )
                    )
                    or (
                        existing.password
                        != (
                            fresh.password
                            or ""
                        )
                    )
                )

                was_enabled = (
                    self.is_camera_enabled(
                        existing
                    )
                )

                # -------------------------------------------------
                # Stop before changing connection settings.
                # -------------------------------------------------

                if connection_changed:

                    self.stop_camera(
                        existing
                    )

                # -------------------------------------------------
                # Update SAME object.
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
                # Rebuild URL if connection changed.
                # -------------------------------------------------

                if connection_changed:

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

                # -------------------------------------------------
                # Enforce new status.
                # -------------------------------------------------

                if not self.is_camera_enabled(
                    existing
                ):

                    self.stop_camera(
                        existing
                    )

                elif connection_changed:

                    self.start_camera(
                        existing
                    )

                elif not was_enabled:

                    self.start_camera(
                        existing
                    )

            # =====================================================
            # FIND DELETED CAMERAS
            # =====================================================

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

            # =====================================================
            # STOP DELETED CAMERA STREAMS
            # =====================================================

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

            # =====================================================
            # REPLACE REGISTRY
            # =====================================================

            with self.camera_lock:

                self.cameras = (
                    new_cameras
                )

            # =====================================================
            # HANDLE NEW CAMERAS
            # =====================================================

            #
            # New cameras were not in old_by_id.
            #
            # Start them only when status is ON.
            #

            for camera in new_cameras:

                if camera.id not in old_by_id:

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
    # CAMERA STREAM RECONCILIATION
    # =============================================================

    def reconcile_camera_stream(
        self,
        camera,
        connection_changed=False
    ):
        """
        Force a camera's runtime stream state to match its status.

        This is useful after external changes to a Camera object.

        Rules:

            OFF:
                Stop.

            ON + connection changed:
                Stop, then restart.

            ON:
                Start if needed.
        """

        if camera is None:

            return False

        if not self.is_camera_enabled(
            camera
        ):

            self.stop_camera(
                camera
            )

            return False

        if connection_changed:

            self.stop_camera(
                camera
            )

        return self.start_camera(
            camera
        )

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

        Page on_hide() is only for page-specific resources such as:

            - PLC monitoring
            - timers
            - animations
            - GUI previews
            - temporary callbacks

        A page MUST NOT stop shared Camera workers in on_hide().
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

        # =========================================================
        # HIDE CURRENT PAGE
        # =========================================================

        if (
            self.current_frame is not None
            and
            self.current_frame
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

        # =========================================================
        # SWITCH PAGE
        # =========================================================

        self.current_frame = (
            target_frame
        )

        target_frame.tkraise()

        # =========================================================
        # SHOW TARGET PAGE
        # =========================================================

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

        This only changes GUI layout.

        It does not control global camera lifecycle.
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

        This is the ONLY normal place where all shared camera
        streams are stopped globally.
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
        # We do NOT call:
        #
        #     frame.stop_all_cameras()
        #
        # CameraApp already owns and stopped all camera streams.
        #
        # Pages may clean up their own non-camera resources.
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

        # =========================================================
        # EXIT PROCESS
        # =========================================================

        sys.exit(0)
    def update_camera_stream(self, camera, connection_changed=False):
        if camera is None:
            return

        # Disabled / maintenance cameras NEVER run
        if not getattr(camera, "status", False):
            self.stop_camera(camera)
            return

        # Connection settings changed:
        # restart the stream using the new RTSP URL.
        if connection_changed:
            self.stop_camera(camera)

        # Enabled cameras should be running.
        self.start_camera(camera)
