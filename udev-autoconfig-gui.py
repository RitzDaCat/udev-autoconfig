#!/usr/bin/env python3

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, GLib, Gio, Pango
import os
import sys
import subprocess
import threading
from pathlib import Path
from typing import List, Dict, Optional
import re
import types

# Import the existing backend classes from the main script
import importlib.util

# Try to find the udev-autoconfig.py script
try:
    # First try relative to this script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    udev_script_path = os.path.join(script_dir, "udev-autoconfig.py")
except NameError:
    # If __file__ is not defined (e.g., in exec context), use current directory
    udev_script_path = os.path.join(os.getcwd(), "udev-autoconfig.py")

# Also check standard installation path
if not os.path.exists(udev_script_path):
    if os.path.exists("/usr/local/bin/udev-autoconfig"):
        udev_script_path = "/usr/local/bin/udev-autoconfig"

# Load the module - handle files without .py extension
if udev_script_path.endswith('.py'):
    spec = importlib.util.spec_from_file_location("udev_autoconfig", udev_script_path)
    udev_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(udev_module)
else:
    # For files without .py extension, use exec
    import types
    udev_module = types.ModuleType("udev_autoconfig")
    with open(udev_script_path, 'r') as f:
        exec(f.read(), udev_module.__dict__)
    sys.modules["udev_autoconfig"] = udev_module
UdevDevice = udev_module.UdevDevice
UdevRuleGenerator = udev_module.UdevRuleGenerator

class DeviceRow(Gtk.Box):
    """Custom widget for displaying a USB device in the list"""
    
    def __init__(self, device: UdevDevice, index: int, has_rule: bool = False):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self.device = device
        self.index = index
        
        # Checkbox for selection
        self.checkbox = Gtk.CheckButton()
        self.checkbox.set_margin_start(12)
        self.checkbox.set_margin_end(8)
        self.checkbox.set_active(False)  # Start unchecked, let user choose
        self.append(self.checkbox)
        
        # Device info box
        info_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        info_box.set_hexpand(True)
        
        # Device name
        name_label = Gtk.Label()
        device_name = f"{device.vendor_name or 'Unknown'} {device.product_name or 'Device'}"
        name_label.set_markup(f"<b>{device_name}</b>")
        name_label.set_halign(Gtk.Align.START)
        info_box.append(name_label)
        
        # Device IDs and subsystem
        details_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        
        id_label = Gtk.Label(label=f"[{device.vendor_id}:{device.product_id}]")
        id_label.set_opacity(0.7)
        id_label.set_halign(Gtk.Align.START)
        details_box.append(id_label)
        
        subsystem_label = Gtk.Label(label=f"({device.subsystem})")
        subsystem_label.set_opacity(0.7)
        details_box.append(subsystem_label)
        
        if device.devname:
            devname_label = Gtk.Label(label=f"→ {device.devname}")
            devname_label.set_opacity(0.5)
            devname_label.set_ellipsize(Pango.EllipsizeMode.END)
            details_box.append(devname_label)
        
        info_box.append(details_box)
        self.append(info_box)
        
        # Status indicator
        status_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        status_box.set_margin_end(12)
        
        if has_rule:
            status_icon = Gtk.Image.new_from_icon_name("emblem-ok-symbolic")
            status_icon.set_pixel_size(16)
            status_label = Gtk.Label(label="Configured")
            status_label.add_css_class("success")
        else:
            status_icon = Gtk.Image.new_from_icon_name("dialog-warning-symbolic")
            status_icon.set_pixel_size(16)
            status_label = Gtk.Label(label="Needs rule")
            status_label.add_css_class("warning")
        
        status_box.append(status_icon)
        status_box.append(status_label)
        self.append(status_box)
        
        # Add some padding
        self.set_margin_top(8)
        self.set_margin_bottom(8)
    
    def is_selected(self) -> bool:
        return self.checkbox.get_active()
    
    def set_selected(self, selected: bool):
        self.checkbox.set_active(selected)


class UdevConfigWindow(Adw.ApplicationWindow):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        self.generator = UdevRuleGenerator()
        self.device_rows = []
        self.devices = []
        
        # Set up window
        self.set_title("USB Device Configuration")
        self.set_default_size(800, 600)
        
        # Create header bar
        header = Adw.HeaderBar()
        
        # Add menu button
        menu_button = Gtk.MenuButton()
        menu_button.set_icon_name("open-menu-symbolic")
        
        menu = Gio.Menu()
        menu.append("About", "app.about")
        menu.append("Quit", "app.quit")
        menu_button.set_menu_model(menu)
        
        header.pack_end(menu_button)
        
        # Add refresh button
        self.refresh_button = Gtk.Button()
        self.refresh_button.set_icon_name("view-refresh-symbolic")
        self.refresh_button.set_tooltip_text("Refresh device list")
        self.refresh_button.connect("clicked", self.on_refresh_clicked)
        header.pack_start(self.refresh_button)
        
        # Main layout
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        main_box.append(header)
        
        # Create toast overlay for notifications
        self.toast_overlay = Adw.ToastOverlay()
        
        # Content box
        content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        content_box.set_margin_top(12)
        content_box.set_margin_bottom(12)
        content_box.set_margin_start(12)
        content_box.set_margin_end(12)
        
        # Info bar for sudo requirement
        self.info_bar = Adw.Banner()
        self.info_bar.set_title("Administrator privileges required")
        self.info_bar.set_button_label("Run as Admin")
        self.info_bar.connect("button-clicked", self.on_run_as_admin)
        content_box.append(self.info_bar)
        
        # Summary info box
        self.summary_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        self.summary_box.set_halign(Gtk.Align.CENTER)
        self.summary_box.set_margin_top(8)
        self.summary_box.set_margin_bottom(8)
        self.summary_box.add_css_class("dim-label")
        
        self.total_devices_label = Gtk.Label()
        self.configured_count_label = Gtk.Label()
        self.unconfigured_count_label = Gtk.Label()
        
        self.summary_box.append(self.total_devices_label)
        self.summary_box.append(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL))
        self.summary_box.append(self.configured_count_label)
        self.summary_box.append(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL))
        self.summary_box.append(self.unconfigured_count_label)
        
        content_box.append(self.summary_box)
        
        # Create notebook for tabbed view
        self.notebook = Gtk.Notebook()
        self.notebook.set_vexpand(True)
        
        # Tab 1: Devices needing configuration
        unconfigured_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        unconfigured_box.set_margin_top(8)
        unconfigured_box.set_margin_bottom(8)
        unconfigured_box.set_margin_start(8)
        unconfigured_box.set_margin_end(8)
        
        # Header for unconfigured devices
        unconfigured_header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        unconfigured_header.set_margin_bottom(8)
        
        unconfigured_title = Gtk.Label()
        unconfigured_title.set_markup("<b>Devices Without Rules</b>")
        unconfigured_title.set_halign(Gtk.Align.START)
        unconfigured_header.append(unconfigured_title)
        
        # Select all/none buttons for unconfigured
        select_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        select_box.set_hexpand(True)
        select_box.set_halign(Gtk.Align.END)
        
        select_all_btn = Gtk.Button(label="Select All")
        select_all_btn.connect("clicked", self.on_select_all_unconfigured)
        select_all_btn.add_css_class("flat")
        select_box.append(select_all_btn)
        
        select_none_btn = Gtk.Button(label="Select None")
        select_none_btn.connect("clicked", self.on_select_none)
        select_none_btn.add_css_class("flat")
        select_box.append(select_none_btn)
        
        unconfigured_header.append(select_box)
        unconfigured_box.append(unconfigured_header)
        
        # Scrolled window for unconfigured devices
        unconfigured_scrolled = Gtk.ScrolledWindow()
        unconfigured_scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        unconfigured_scrolled.set_vexpand(True)
        unconfigured_scrolled.set_min_content_height(250)
        
        # Unconfigured device list
        self.unconfigured_list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self.unconfigured_list.add_css_class("card")
        unconfigured_scrolled.set_child(self.unconfigured_list)
        unconfigured_box.append(unconfigured_scrolled)
        
        # Tab 2: Already configured devices
        configured_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        configured_box.set_margin_top(8)
        configured_box.set_margin_bottom(8)
        configured_box.set_margin_start(8)
        configured_box.set_margin_end(8)
        
        # Header for configured devices
        configured_header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        configured_header.set_margin_bottom(8)
        
        configured_title = Gtk.Label()
        configured_title.set_markup("<b>Devices With Existing Rules</b>")
        configured_title.set_halign(Gtk.Align.START)
        configured_header.append(configured_title)
        configured_box.append(configured_header)
        
        # Scrolled window for configured devices
        configured_scrolled = Gtk.ScrolledWindow()
        configured_scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        configured_scrolled.set_vexpand(True)
        configured_scrolled.set_min_content_height(250)
        
        # Configured device list
        self.configured_list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self.configured_list.add_css_class("card")
        configured_scrolled.set_child(self.configured_list)
        configured_box.append(configured_scrolled)
        
        # Add tabs to notebook
        self.notebook.append_page(unconfigured_box, Gtk.Label(label="Needs Configuration"))
        self.notebook.append_page(configured_box, Gtk.Label(label="Already Configured"))
        
        content_box.append(self.notebook)
        
        # Progress bar
        self.progress_bar = Gtk.ProgressBar()
        self.progress_bar.set_visible(False)
        self.progress_bar.set_show_text(True)
        content_box.append(self.progress_bar)
        
        # Action buttons
        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        button_box.set_halign(Gtk.Align.CENTER)
        button_box.set_margin_top(12)
        
        # Dry run button
        self.dry_run_button = Gtk.Button(label="Preview Rules")
        self.dry_run_button.set_tooltip_text("Show what rules would be created without applying them")
        self.dry_run_button.connect("clicked", self.on_dry_run_clicked)
        self.dry_run_button.add_css_class("flat")
        button_box.append(self.dry_run_button)
        
        # Apply button
        self.apply_button = Gtk.Button(label="Create Rules")
        self.apply_button.set_tooltip_text("Create and apply udev rules for selected devices")
        self.apply_button.connect("clicked", self.on_apply_clicked)
        self.apply_button.add_css_class("suggested-action")
        self.apply_button.set_size_request(150, -1)
        button_box.append(self.apply_button)
        
        content_box.append(button_box)
        
        # Add content to toast overlay
        self.toast_overlay.set_child(content_box)
        main_box.append(self.toast_overlay)
        
        self.set_content(main_box)
        
        # Check if running as root
        self.check_sudo_status()
        
        # Load devices on startup
        self.load_devices()
        
        # Apply CSS for custom styling
        self.apply_css()
    
    def apply_css(self):
        css_provider = Gtk.CssProvider()
        css = """
        .success {
            color: @success_color;
        }
        .warning {
            color: @warning_color;
        }
        .card {
            background: @card_bg_color;
            border-radius: 12px;
            border: 1px solid alpha(@borders, 0.5);
        }
        """
        css_provider.load_from_data(css.encode())
        Gtk.StyleContext.add_provider_for_display(
            self.get_display(),
            css_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
    
    def check_sudo_status(self):
        """Check if running with sudo privileges"""
        if os.geteuid() == 0:
            self.info_bar.set_visible(False)
            self.apply_button.set_sensitive(True)
        else:
            self.info_bar.set_visible(True)
            self.info_bar.set_revealed(True)
            self.apply_button.set_sensitive(False)
    
    def on_run_as_admin(self, *args):
        """Restart the application with sudo privileges"""
        try:
            # Get the path to this script
            script_path = os.path.abspath(__file__)
            # Try to use pkexec for graphical sudo
            subprocess.Popen(['pkexec', sys.executable, script_path])
            self.get_application().quit()
        except Exception as e:
            self.show_toast(f"Failed to restart with admin privileges: {e}", error=True)
    
    def load_devices(self):
        """Load USB devices in a background thread"""
        self.set_loading(True)
        
        def load_thread():
            try:
                devices = self.generator.get_usb_devices()
                existing_rules = self.generator.get_existing_rules()
                GLib.idle_add(self.display_devices, devices, existing_rules)
            except Exception as e:
                GLib.idle_add(self.show_toast, f"Error loading devices: {e}", True)
                GLib.idle_add(self.set_loading, False)
        
        thread = threading.Thread(target=load_thread)
        thread.daemon = True
        thread.start()
    
    def display_devices(self, devices: List[UdevDevice], existing_rules: Dict[str, List[str]]):
        """Display devices in separate lists for configured and unconfigured"""
        # Clear existing lists
        while child := self.unconfigured_list.get_first_child():
            self.unconfigured_list.remove(child)
        while child := self.configured_list.get_first_child():
            self.configured_list.remove(child)
        
        self.device_rows = []
        self.devices = devices
        
        if not devices:
            label = Gtk.Label(label="No USB devices found")
            label.set_margin_top(32)
            label.set_margin_bottom(32)
            self.unconfigured_list.append(label)
            self.set_loading(False)
            return
        
        unconfigured_devices = []
        configured_devices = []
        
        # Separate devices into configured and unconfigured
        for device in devices:
            has_rule = False
            if existing_rules and device.vendor_id and device.product_id:
                vid = device.vendor_id.lower()
                pid = device.product_id.lower()
                has_rule = vid in existing_rules and pid in existing_rules.get(vid, [])
            
            if has_rule:
                configured_devices.append((device, has_rule))
            else:
                unconfigured_devices.append((device, has_rule))
        
        # Add unconfigured devices
        if unconfigured_devices:
            for i, (device, has_rule) in enumerate(unconfigured_devices):
                row = DeviceRow(device, i, has_rule)
                self.device_rows.append(row)
                
                if i > 0:
                    separator = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
                    self.unconfigured_list.append(separator)
                
                self.unconfigured_list.append(row)
        else:
            label = Gtk.Label(label="All devices are configured! ✅")
            label.set_margin_top(32)
            label.set_margin_bottom(32)
            self.unconfigured_list.append(label)
        
        # Add configured devices
        if configured_devices:
            for i, (device, has_rule) in enumerate(configured_devices):
                row = DeviceRow(device, len(unconfigured_devices) + i, has_rule)
                self.device_rows.append(row)
                
                if i > 0:
                    separator = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
                    self.configured_list.append(separator)
                
                self.configured_list.append(row)
        else:
            label = Gtk.Label(label="No configured devices found")
            label.set_margin_top(32)
            label.set_margin_bottom(32)
            self.configured_list.append(label)
        
        self.set_loading(False)
        
        # Update notebook tab labels with counts
        unconfigured_label = self.notebook.get_tab_label(self.notebook.get_nth_page(0))
        configured_label = self.notebook.get_tab_label(self.notebook.get_nth_page(1))
        
        if unconfigured_label:
            unconfigured_label.set_text(f"Needs Configuration ({len(unconfigured_devices)})")
        if configured_label:
            configured_label.set_text(f"Already Configured ({len(configured_devices)})")
        
        # Update summary labels
        self.total_devices_label.set_text(f"Total Devices: {len(devices)}")
        self.configured_count_label.set_markup(f"<span color='#26a269'>✓ Configured: {len(configured_devices)}</span>")
        self.unconfigured_count_label.set_markup(f"<span color='#f6d32d'>⚠ Needs Rules: {len(unconfigured_devices)}</span>")
        
        # Show a toast with device count
        if len(unconfigured_devices) > 0:
            self.show_toast(f"Found {len(unconfigured_devices)} device(s) without rules. Select which ones to configure.")
        else:
            self.show_toast("All devices are already configured!")
    
    def get_selected_devices(self) -> List[UdevDevice]:
        """Get list of selected devices"""
        selected = []
        for row in self.device_rows:
            if row.is_selected():
                selected.append(row.device)
        return selected
    
    def on_select_all_unconfigured(self, button):
        """Select all unconfigured devices"""
        for row in self.device_rows:
            # Only select if the device doesn't have a rule (checkbox would be active by default)
            if not row.device.vendor_id or not row.device.product_id:
                continue
            generator = UdevRuleGenerator()
            existing = generator.get_existing_rules()
            vid = row.device.vendor_id.lower()
            pid = row.device.product_id.lower()
            has_rule = vid in existing and pid in existing.get(vid, [])
            if not has_rule:
                row.set_selected(True)
    
    def on_select_none(self, button):
        """Deselect all devices"""
        for row in self.device_rows:
            row.set_selected(False)
    
    def on_refresh_clicked(self, button):
        """Refresh the device list"""
        self.load_devices()
    
    def on_dry_run_clicked(self, button):
        """Show preview of rules that would be created"""
        selected = self.get_selected_devices()
        if not selected:
            self.show_toast("No devices selected", error=True)
            return
        
        # Create a dialog to show the preview
        dialog = Adw.MessageDialog(transient_for=self)
        dialog.set_heading("Rule Preview")
        dialog.set_body_use_markup(True)
        
        # Generate preview text
        preview_text = []
        for device in selected:
            rule = self.generator.generate_rule(device)
            device_name = f"{device.vendor_name or 'Unknown'} {device.product_name or 'Device'}"
            preview_text.append(f"<b>{device_name}</b> [{device.vendor_id}:{device.product_id}]\n")
            
            # Format the rules with monospace
            rule_lines = rule.split('\n')
            for line in rule_lines[:3]:  # Show first 3 lines of rules
                if line and not line.startswith('#'):
                    preview_text.append(f"<tt>{GLib.markup_escape_text(line[:80])}</tt>\n")
            preview_text.append("")
        
        body_text = "The following rules would be created:\n\n" + "".join(preview_text)
        dialog.set_body(body_text[:2000])  # Limit preview length
        
        dialog.add_response("close", "Close")
        dialog.set_default_response("close")
        dialog.set_close_response("close")
        
        dialog.present()
    
    def on_apply_clicked(self, button):
        """Apply udev rules for selected devices"""
        selected = self.get_selected_devices()
        if not selected:
            self.show_toast("No devices selected", error=True)
            return
        
        # Confirm action
        dialog = Adw.MessageDialog(transient_for=self)
        dialog.set_heading("Create udev rules?")
        dialog.set_body(f"This will create udev rules for {len(selected)} selected device(s).")
        
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("apply", "Create Rules")
        dialog.set_response_appearance("apply", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response("cancel")
        dialog.set_close_response("cancel")
        
        dialog.connect("response", self.on_apply_confirmed, selected)
        dialog.present()
    
    def on_apply_confirmed(self, dialog, response, selected_devices):
        """Handle confirmation dialog response"""
        if response != "apply":
            return
        
        self.set_loading(True)
        self.progress_bar.set_text("Creating rules...")
        
        def apply_thread():
            try:
                # Save rules
                saved = self.generator.save_rules(selected_devices, dry_run=False)
                
                if saved:
                    GLib.idle_add(self.progress_bar.set_text, "Applying rules...")
                    GLib.idle_add(self.progress_bar.set_fraction, 0.5)
                    
                    # Reload udev rules
                    subprocess.run(['udevadm', 'control', '--reload-rules'], check=True)
                    subprocess.run(['udevadm', 'trigger'], check=True)
                    
                    GLib.idle_add(self.progress_bar.set_fraction, 1.0)
                    GLib.idle_add(self.show_toast, f"Rules created successfully for {len(selected_devices)} device(s)!")
                    GLib.idle_add(self.load_devices)  # Refresh the list
                else:
                    GLib.idle_add(self.show_toast, "No new rules were created", True)
                
            except subprocess.CalledProcessError as e:
                GLib.idle_add(self.show_toast, f"Failed to apply rules: {e}", True)
            except Exception as e:
                GLib.idle_add(self.show_toast, f"Error: {e}", True)
            finally:
                GLib.idle_add(self.set_loading, False)
        
        thread = threading.Thread(target=apply_thread)
        thread.daemon = True
        thread.start()
    
    def set_loading(self, loading: bool):
        """Set loading state"""
        self.refresh_button.set_sensitive(not loading)
        self.apply_button.set_sensitive(not loading and os.geteuid() == 0)
        self.dry_run_button.set_sensitive(not loading)
        self.progress_bar.set_visible(loading)
        if not loading:
            self.progress_bar.set_fraction(0)
            self.progress_bar.set_text("")
    
    def show_toast(self, message: str, error: bool = False):
        """Show a toast notification"""
        toast = Adw.Toast(title=message)
        toast.set_timeout(3 if not error else 5)
        self.toast_overlay.add_toast(toast)


class UdevConfigApp(Adw.Application):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.connect('activate', self.on_activate)
        
        # Set up actions
        self.setup_actions()
    
    def setup_actions(self):
        """Set up application actions"""
        # Quit action
        quit_action = Gio.SimpleAction.new("quit", None)
        quit_action.connect("activate", lambda *_: self.quit())
        self.add_action(quit_action)
        
        # About action
        about_action = Gio.SimpleAction.new("about", None)
        about_action.connect("activate", self.on_about)
        self.add_action(about_action)
    
    def on_activate(self, app):
        self.win = UdevConfigWindow(application=app)
        self.win.present()
    
    def on_about(self, action, param):
        """Show about dialog"""
        about = Adw.AboutWindow(
            transient_for=self.get_active_window(),
            application_name="USB Device Configuration",
            application_icon="preferences-system",
            developer_name="USB Device Auto-Config",
            version="1.0.0",
            developers=["USB Device Auto-Config Contributors"],
            copyright="© 2024 USB Device Auto-Config",
            website="https://github.com/RitzDaCat/udev-autoconfig",
            issue_url="https://github.com/RitzDaCat/udev-autoconfig/issues",
            license_type=Gtk.License.MIT_X11,
            comments="Automatically configure udev rules for USB devices on Linux"
        )
        about.present()


def main():
    app = UdevConfigApp(application_id='com.github.udev-autoconfig')
    return app.run(sys.argv)


if __name__ == '__main__':
    sys.exit(main())