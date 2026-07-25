import tkinter as tk
import cv2
from PIL import Image, ImageTk
import threading
import random
import time


class CentralPreview(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent, bg="black")

        self.controller = controller

        self.current_cam = None
        self.is_plc_triggered = False

        self.running = False
        self.after_id = None

        # PLC / AUTO mode
        self.plc_mode = True
        self.plc_fail_count = 0
        self.max_plc_fails = 3
        self.plc_fail_start_time = None

        self.last_auto_switch = time.time()

        # PLC reader
        self.plc = None

        # Spinner
        self.spinner_chars = [
            "⠋", "⠙", "⠹", "⠸", "⠼",
            "⠴", "⠦", "⠧", "⠇", "⠏"
        ]
        self.spinner_index = 0
        self.spinner_after_id = None

        self._build_ui()

    # =========================================================
    # UI
    # =========================================================

    def _build_ui(self):

        # =====================================================
        # TOP HEADER BAR
        # =====================================================

        self.top_bar = tk.Frame(
            self,
            bg="#1e1e1e",
            height=48
        )

        self.top_bar.pack(
            fill="x",
            side="top"
        )

        self.top_bar.pack_propagate(False)

        # -----------------------------------------------------
        # Zone label - LEFT
        # -----------------------------------------------------

        self.zone_label = tk.Label(
            self.top_bar,
            text="zone: --",
            font=("Arial", 15, "bold"),
            bg="#1e1e1e",
            fg="#aaaaaa"
        )

        self.zone_label.pack(
            side="left",
            padx=15
        )

        # -----------------------------------------------------
        # Mode indicator - RIGHT
        # -----------------------------------------------------

        self.mode_label = tk.Label(
            self.top_bar,
            text="PLC MODE",
            font=("Arial", 12, "bold"),
            bg="#1e1e1e",
            fg="#00ddff"
        )

        self.mode_label.pack(
            side="right",
            padx=(10, 15)
        )

        # -----------------------------------------------------
        # Mode switching button
        #
        # This is now in the header instead of below the
        # camera preview.
        # -----------------------------------------------------

        self.mode_btn = tk.Button(
            self.top_bar,
            text="Switch to AUTO Mode",
            font=("Arial", 10, "bold"),
            bg="#ff8800",
            fg="white",
            activebackground="#ff9900",
            activeforeground="white",
            relief="flat",
            bd=0,
            padx=12,
            pady=5,
            cursor="hand2",
            command=self.toggle_mode
        )

        self.mode_btn.pack(
            side="right",
            padx=5
        )

        # =====================================================
        # TRIGGER BORDER
        # =====================================================

        self.border_frame = tk.Frame(
            self,
            bg="#1e1e1e",
            height=6
        )

        self.border_frame.pack(
            fill="x",
            side="top"
        )

        self.border_frame.pack_propagate(False)

        # =====================================================
        # MAIN PREVIEW
        # =====================================================

        self.preview_container = tk.Frame(
            self,
            bg="black"
        )

        self.preview_container.pack(
            fill="both",
            expand=True,
            padx=8,
            pady=8
        )

        self.preview_label = tk.Label(
            self.preview_container,
            bg="black",
            fg="#ff6666",
            anchor="center"
        )

        self.preview_label.pack(
            fill="both",
            expand=True
        )

    # =========================================================
    # SPINNER
    # =========================================================

    def _start_connecting_spinner(
        self,
        message,
        color="#00ccff"
    ):

        self._stop_connecting_spinner()

        if not self.running:
            return

        self.spinner_index = (
            self.spinner_index + 1
        ) % len(self.spinner_chars)

        spinner = self.spinner_chars[
            self.spinner_index
        ]

        self.preview_label.configure(
            text=f"{message} {spinner}",
            fg=color,
            font=("Arial", 14, "bold"),
            image=""
        )

        self.preview_label.image = None

        self.spinner_after_id = self.after(
            80,
            lambda: self._start_connecting_spinner(
                message,
                color
            )
        )

    def _stop_connecting_spinner(self):

        if self.spinner_after_id is not None:

            try:
                self.after_cancel(
                    self.spinner_after_id
                )

            except Exception:
                pass

        self.spinner_after_id = None

    def _show_connecting_message(self):

        # Don't show PLC UI in AUTO mode
        if not self.plc_mode:
            return

        # Spinner already running
        if self.spinner_after_id is not None:
            return

        self._clear_preview()

        self._start_connecting_spinner(
            "Connecting to PLC",
            "#00ccff"
        )

    def _show_connecting_cameras_message(self):

        if self.plc_mode:
            return

        self._stop_connecting_spinner()

        self._clear_preview()

        self._start_connecting_spinner(
            "Connecting to cameras",
            "#ffaa00"
        )

    # =========================================================
    # PLC
    # =========================================================

    def set_plc(self, plc_reader):
        self.plc = plc_reader

    # =========================================================
    # START / STOP
    # =========================================================

    def start(self):

        if self.running:
            return

        self.running = True

        # Make sure the correct mode is reflected in the UI
        self._update_mode_ui()

        threading.Thread(
            target=self._monitor_loop,
            daemon=True,
            name="CentralPreviewMonitor"
        ).start()

    def stop(self):

        self.running = False

        self._stop_connecting_spinner()

        if self.after_id is not None:

            try:
                self.after_cancel(
                    self.after_id
                )

            except Exception:
                pass

            self.after_id = None

    # =========================================================
    # PREVIEW MANAGEMENT
    # =========================================================

    def _clear_preview(self):

        self.current_cam = None

        self.preview_label.image = None

        self.preview_label.configure(
            image="",
            text=""
        )

    # =========================================================
    # MODE SWITCHING
    # =========================================================

    def toggle_mode(self):

        self._stop_connecting_spinner()

        self._clear_preview()

        self.plc_mode = not self.plc_mode

        self.plc_fail_count = 0
        self.plc_fail_start_time = time.time()

        self.current_cam = None
        self.is_plc_triggered = False

        self._update_mode_ui()

        self._update_zone_label()
        self._update_border()

        # =====================================================
        # PLC MODE
        # =====================================================

        if self.plc_mode:

            self.last_auto_switch = time.time()

            self._show_connecting_message()

        # =====================================================
        # AUTO MODE
        # =====================================================

        else:

            self.last_auto_switch = time.time()

            self._show_connecting_cameras_message()

            self.after(
                1500,
                self._switch_to_random_online_camera
            )

    def _update_mode_ui(self):

        if self.plc_mode:

            # PLC mode
            self.mode_label.configure(
                text="PLC MODE",
                fg="#00ddff"
            )

            self.mode_btn.configure(
                text="Switch to AUTO Mode",
                bg="#ff8800",
                activebackground="#ff9900"
            )

        else:

            # AUTO mode
            self.mode_label.configure(
                text="AUTO MODE",
                fg="#ffaa00"
            )

            self.mode_btn.configure(
                text="Switch to PLC Mode",
                bg="#0088ff",
                activebackground="#0099ff"
            )

    # =========================================================
    # MONITOR LOOP
    # =========================================================

    def _monitor_loop(self):

        self.plc_fail_start_time = None

        while self.running:

            try:

                # =================================================
                # PLC MODE
                # =================================================

                if self.plc_mode and self.plc:

                    cnum = (
                        self.plc.read_camera_number()
                    )

                    if cnum > 0:

                        # PLC recovered
                        self.plc_fail_count = 0
                        self.plc_fail_start_time = None

                        self.after(
                            0,
                            lambda n=cnum:
                            self._switch_to_camera(
                                n,
                                plc_triggered=True
                            )
                        )

                    else:

                        self._handle_plc_failure()

                # =================================================
                # AUTO MODE
                # =================================================

                elif not self.plc_mode:

                    if (
                        time.time()
                        - self.last_auto_switch
                        > 20
                    ):

                        self.after(
                            0,
                            self._switch_to_random_online_camera
                        )

                        self.last_auto_switch = (
                            time.time()
                        )

            except Exception as e:

                print(
                    f"[CentralPreview] Monitor error: {e}"
                )

                self._handle_plc_failure()

            time.sleep(0.8)

    # =========================================================
    # CAMERA SWITCHING
    # =========================================================

    def _switch_to_camera(
        self,
        modbus_num,
        plc_triggered=False
    ):

        # Ignore PLC requests when currently in AUTO mode
        if plc_triggered and not self.plc_mode:
            return

        self._stop_connecting_spinner()

        self._clear_preview()

        for card in self.controller.camera_cards.values():

            if card.cam.modbus == modbus_num:

                self.current_cam = card.cam

                self.is_plc_triggered = (
                    plc_triggered
                )

                self._update_zone_label()
                self._update_border()

                self._start_preview()

                return

    def _switch_to_random_online_camera(self):

        if self.plc_mode:
            return

        self._stop_connecting_spinner()

        online_cams = [
            card.cam
            for card in self.controller.camera_cards.values()
            if (
                getattr(card.cam, "status", 1)
                and card.cam.is_online()
            )
        ]

        if not online_cams:
            return

        self._clear_preview()

        self.current_cam = random.choice(
            online_cams
        )

        self.is_plc_triggered = False

        self._update_zone_label()
        self._update_border()

        self._start_preview()

    # =========================================================
    # PLC FAILURE
    # =========================================================

    def _handle_plc_failure(self):

        # Ignore PLC failures in AUTO mode
        if not self.plc_mode:
            return

        self.after(
            0,
            self._show_connecting_message
        )

        self.plc_fail_count += 1

        # Start timer only once
        if self.plc_fail_start_time is None:

            self.plc_fail_start_time = (
                time.time()
            )

        elapsed = (
            time.time()
            - self.plc_fail_start_time
        )

        fail_condition = (
            self.plc_fail_count
            >= self.max_plc_fails
            or elapsed >= 5
        )

        if fail_condition:

            # Double-check mode before switching
            if self.plc_mode:

                self.after(
                    0,
                    self._force_auto_mode
                )

    def _force_auto_mode(self):

        if not self.plc_mode:
            return

        self.plc_mode = False

        self.plc_fail_count = 0

        self.last_auto_switch = (
            time.time()
        )

        self._update_mode_ui()

        self._show_plc_failed_message()

        # Show "connecting to cameras"
        self.after(
            1500,
            self._show_connecting_cameras_message
        )

        # Select camera
        self.after(
            3000,
            self._switch_to_random_online_camera
        )

    # =========================================================
    # UI STATUS
    # =========================================================

    def _update_zone_label(self):

        if self.current_cam:

            color = (
                "#ff4444"
                if self.is_plc_triggered
                else "#00ff88"
            )

            name = (
                self.current_cam.name
                or "Unknown"
            )

            self.zone_label.configure(
                text=(
                    f"zone: "
                    f"{self.current_cam.modbus}"
                    f" - {name}"
                ),
                fg=color
            )

        else:

            self.zone_label.configure(
                text="zone: --",
                fg="#aaaaaa"
            )

    def _update_border(self):

        self.border_frame.configure(
            bg=(
                "red"
                if self.is_plc_triggered
                else "#1e1e1e"
            ),
            height=6
        )

    # =========================================================
    # PREVIEW
    # =========================================================

    def _start_preview(self):

        if self.current_cam:

            self.current_cam.start()

            self._update_frame()

    def _update_frame(self):

        if (
            not self.running
            or not self.current_cam
        ):
            return

        frame = (
            self.current_cam.get_frame()
        )

        if frame is not None:

            label_w = (
                self.preview_label.winfo_width()
            )

            label_h = (
                self.preview_label.winfo_height()
            )

            if (
                label_w > 100
                and label_h > 100
            ):

                h, w = frame.shape[:2]

                aspect = (
                    w / h
                )

                new_w = label_w

                new_h = int(
                    new_w / aspect
                )

                # Keep the entire frame visible
                if new_h > label_h:

                    new_h = label_h

                    new_w = int(
                        new_h * aspect
                    )

                frame = cv2.resize(
                    frame,
                    (new_w, new_h),
                    interpolation=cv2.INTER_AREA
                )

            frame = cv2.cvtColor(
                frame,
                cv2.COLOR_BGR2RGB
            )

            photo = ImageTk.PhotoImage(
                Image.fromarray(frame)
            )

            self.preview_label.configure(
                image=photo,
                text=""
            )

            # Keep reference alive
            self.preview_label.image = photo

        else:

            self.preview_label.configure(
                image="",
                text="No Signal",
                fg="#ff6666"
            )

            self.preview_label.image = None

        self.after_id = self.after(
            40,
            self._update_frame
        )

    # =========================================================
    # PLC FAILURE MESSAGE
    # =========================================================

    def _show_plc_failed_message(self):

        self._stop_connecting_spinner()

        self._update_mode_ui()

        self.preview_label.configure(
            text=(
                "Failed Connecting to PLC\n"
                "Switching to Auto Mode"
            ),
            fg="#ffaa00",
            font=("Arial", 14, "bold"),
            image=""
        )

        self.preview_label.image = None