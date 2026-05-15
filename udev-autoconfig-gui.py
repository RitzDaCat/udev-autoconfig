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

# Import the existing backend classes from the main script
import importlib.util
import types


def load_udev_module():
    """
    Load the udev-autoconfig module from various possible locations.
    Search order: system paths first, then local development paths.
    """
    search_paths = [
        "/usr/bin/udev-autoconfig",           # Arch Linux pacman install
        "/usr/local/bin/udev-autoconfig",     # Manual install
    ]
    
    # Add path relative to this script (for development)
    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        search_paths.append(os.path.join(script_dir, "udev-autoconfig.py"))
        search_paths.append(os.path.join(script_dir, "udev-autoconfig"))
    except NameError:
        # __file__ not defined, try current directory
        search_paths.append(os.path.join(os.getcwd(), "udev-autoconfig.py"))
    
    udev_script_path = None
    for path in search_paths:
        if os.path.exists(path):
            udev_script_path = path
            break
    
    if udev_script_path is None:
        raise FileNotFoundError(
            "Could not find udev-autoconfig. Searched:\n  " + 
            "\n  ".join(search_paths)
        )
    
    # Load the module - handle files with or without .py extension
    if udev_script_path.endswith('.py'):
        spec = importlib.util.spec_from_file_location("udev_autoconfig", udev_script_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    else:
        # For files without .py extension (installed executables)
        module = types.ModuleType("udev_autoconfig")
        with open(udev_script_path, 'r', encoding='utf-8') as f:
            code = compile(f.read(), udev_script_path, 'exec')
            exec(code, module.__dict__)
        sys.modules["udev_autoconfig"] = module
    
    return module


udev_module = load_udev_module()
UdevDevice = udev_module.UdevDevice
UdevRuleGenerator = udev_module.UdevRuleGenerator
RulesAuditor = udev_module.RulesAuditor
RuleEntry = udev_module.RuleEntry
DeviceProfile = udev_module.DeviceProfile
DEVICE_PRESETS = udev_module.DEVICE_PRESETS

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
        
        # View Rules button
        self.view_rules_button = Gtk.Button()
        self.view_rules_button.set_icon_name("document-open-symbolic")
        self.view_rules_button.set_tooltip_text("View all rules affecting this device")
        self.view_rules_button.add_css_class("flat")
        self.view_rules_button.set_valign(Gtk.Align.CENTER)
        # Store device reference for the callback
        self.view_rules_button.device = device
        self.append(self.view_rules_button)
        
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
        
        # Info bar for privilege info
        self.info_bar = Adw.Banner()
        self.info_bar.set_title("Admin privileges will be requested when creating rules")
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
        
        # Select all/none buttons for configured devices
        configured_select_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        configured_select_box.set_hexpand(True)
        configured_select_box.set_halign(Gtk.Align.END)
        
        select_all_configured_btn = Gtk.Button(label="Select All")
        select_all_configured_btn.connect("clicked", self.on_select_all_configured)
        select_all_configured_btn.add_css_class("flat")
        configured_select_box.append(select_all_configured_btn)
        
        select_none_configured_btn = Gtk.Button(label="Select None")
        select_none_configured_btn.connect("clicked", self.on_select_none)
        select_none_configured_btn.add_css_class("flat")
        configured_select_box.append(select_none_configured_btn)
        
        configured_header.append(configured_select_box)
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
        
        # Tab 3: Rules Audit
        audit_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        audit_box.set_margin_top(8)
        audit_box.set_margin_bottom(8)
        audit_box.set_margin_start(8)
        audit_box.set_margin_end(8)
        
        # Audit header with scan button and filter
        audit_header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        audit_header.set_margin_bottom(8)
        
        audit_title = Gtk.Label()
        audit_title.set_markup("<b>Rules Audit</b>")
        audit_title.set_halign(Gtk.Align.START)
        audit_header.append(audit_title)
        
        # Filter entry
        self.audit_filter_entry = Gtk.Entry()
        self.audit_filter_entry.set_placeholder_text("Filter by VID:PID or name (e.g., xbox, 045e)")
        self.audit_filter_entry.set_hexpand(True)
        audit_header.append(self.audit_filter_entry)
        
        # Scan button
        self.scan_rules_button = Gtk.Button(label="Scan Rules")
        self.scan_rules_button.connect("clicked", self.on_scan_rules_clicked)
        self.scan_rules_button.add_css_class("suggested-action")
        audit_header.append(self.scan_rules_button)
        
        # Copy to Clipboard button
        self.copy_audit_button = Gtk.Button()
        self.copy_audit_button.set_icon_name("edit-copy-symbolic")
        self.copy_audit_button.set_tooltip_text("Copy results to clipboard for sharing")
        self.copy_audit_button.connect("clicked", self.on_copy_audit_clicked)
        self.copy_audit_button.add_css_class("flat")
        self.copy_audit_button.set_sensitive(False)  # Disabled until scan runs
        audit_header.append(self.copy_audit_button)
        
        # Store audit results as plain text for clipboard
        self.audit_results_text = ""
        
        audit_box.append(audit_header)
        
        # Audit results scrolled window
        audit_scrolled = Gtk.ScrolledWindow()
        audit_scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        audit_scrolled.set_vexpand(True)
        audit_scrolled.set_min_content_height(300)
        
        # Audit results list
        self.audit_results_list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.audit_results_list.add_css_class("card")
        
        # Initial placeholder
        audit_placeholder = Gtk.Label(label="Click 'Scan Rules' to check for duplicates, conflicts, and issues")
        audit_placeholder.set_margin_top(32)
        audit_placeholder.set_margin_bottom(32)
        audit_placeholder.set_opacity(0.7)
        self.audit_results_list.append(audit_placeholder)
        
        audit_scrolled.set_child(self.audit_results_list)
        audit_box.append(audit_scrolled)
        
        self.notebook.append_page(audit_box, Gtk.Label(label="Rules Audit"))
        
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
        
        # Remove rules button
        self.remove_button = Gtk.Button(label="Remove Rules")
        self.remove_button.set_tooltip_text("Remove udev rules for selected configured devices")
        self.remove_button.connect("clicked", self.on_remove_clicked)
        self.remove_button.add_css_class("destructive-action")
        button_box.append(self.remove_button)
        
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
        .status-configured {
            color: @success_color;
        }
        .status-unconfigured {
            color: @warning_color;
        }
        """
        css_provider.load_from_data(css.encode())
        Gtk.StyleContext.add_provider_for_display(
            self.get_display(),
            css_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
    
    def check_sudo_status(self):
        """Check privileges and update UI accordingly"""
        if os.geteuid() == 0:
            # Running as root - hide the info bar
            self.info_bar.set_visible(False)
        else:
            # Running as normal user - show info that admin will be requested when needed
            self.info_bar.set_title("Admin privileges will be requested when creating rules")
            self.info_bar.set_button_label(None)  # Remove the button
            self.info_bar.set_revealed(True)
        
        # Always enable the apply button - we'll use pkexec for the operation
        self.apply_button.set_sensitive(True)
    
    def find_cli_tool(self) -> Optional[str]:
        """Find the udev-autoconfig CLI tool"""
        import shutil
        
        cli_paths = [
            shutil.which('udev-autoconfig'),
            '/usr/bin/udev-autoconfig',
            '/usr/local/bin/udev-autoconfig',
        ]
        
        # Add path relative to this script for development
        try:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            cli_paths.append(os.path.join(script_dir, 'udev-autoconfig.py'))
            cli_paths.append(os.path.join(script_dir, 'udev-autoconfig'))
        except NameError:
            pass
        
        for path in cli_paths:
            if path and os.path.exists(path):
                return path
        return None
    
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
                row.view_rules_button.connect("clicked", self.on_view_rules_clicked)
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
                row.view_rules_button.connect("clicked", self.on_view_rules_clicked)
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
        self.configured_count_label.set_text(f"✓ Configured: {len(configured_devices)}")
        if not self.configured_count_label.has_css_class("status-configured"):
            self.configured_count_label.add_css_class("status-configured")
        self.unconfigured_count_label.set_text(f"⚠ Needs Rules: {len(unconfigured_devices)}")
        if not self.unconfigured_count_label.has_css_class("status-unconfigured"):
            self.unconfigured_count_label.add_css_class("status-unconfigured")
        
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
        # Cache existing rules once instead of per-row
        existing = self.generator.get_existing_rules()
        for row in self.device_rows:
            # Only select if the device doesn't have a rule
            if not row.device.vendor_id or not row.device.product_id:
                continue
            vid = row.device.vendor_id.lower()
            pid = row.device.product_id.lower()
            has_rule = vid in existing and pid in existing.get(vid, [])
            if not has_rule:
                row.set_selected(True)
    
    def on_select_all_configured(self, button):
        """Select all configured devices"""
        existing = self.generator.get_existing_rules()
        for row in self.device_rows:
            if not row.device.vendor_id or not row.device.product_id:
                continue
            vid = row.device.vendor_id.lower()
            pid = row.device.product_id.lower()
            has_rule = vid in existing and pid in existing.get(vid, [])
            if has_rule:
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
    
    def on_view_rules_clicked(self, button):
        """Show all rules files affecting the device"""
        device = button.device
        if not device or not device.vendor_id or not device.product_id:
            self.show_toast("Invalid device", error=True)
            return
        
        vid = device.vendor_id.lower()
        pid = device.product_id.lower()
        device_id = f"{vid}:{pid}"
        device_name = f"{device.vendor_name or 'Unknown'} {device.product_name or 'Device'}"
        
        # Use RulesAuditor to find all rules
        auditor = RulesAuditor()
        auditor.parse_rules()
        
        # Find matching entries
        matching_entries = []
        for entry in auditor.entries:
            entry_vid = entry.vendor_id.lower() if entry.vendor_id else ""
            entry_pid = entry.product_id.lower() if entry.product_id else ""
            
            # Match exact device OR vendor-only rules
            if entry_vid == vid and (entry_pid == pid or not entry_pid):
                matching_entries.append(entry)
        
        # Create dialog
        dialog = Adw.MessageDialog(transient_for=self)
        dialog.set_heading(f"Rules for {device_name}")
        dialog.set_body_use_markup(True)
        
        if matching_entries:
            # Group by file
            files = {}
            for entry in matching_entries:
                fname = entry.filepath.name
                if fname not in files:
                    files[fname] = []
                files[fname].append(entry)
            
            body_parts = [f"<b>Device:</b> <tt>{device_id}</tt>\n"]
            body_parts.append(f"<b>Found {len(matching_entries)} rule(s) in {len(files)} file(s):</b>\n\n")
            
            for fname, entries in files.items():
                body_parts.append(f"<b>📄 {fname}</b>\n")
                for entry in entries[:5]:  # Limit per file
                    mode_str = f'MODE="{entry.mode}"' if entry.mode else ""
                    group_str = f'GROUP="{entry.group}"' if entry.group else ""
                    line_info = f"Line {entry.line_number}: {mode_str} {group_str}"
                    body_parts.append(f"  <tt>{GLib.markup_escape_text(line_info)}</tt>\n")
                if len(entries) > 5:
                    body_parts.append(f"  <i>... and {len(entries) - 5} more</i>\n")
                body_parts.append("\n")
            
            dialog.set_body("".join(body_parts))
        else:
            dialog.set_body(f"<b>Device:</b> <tt>{device_id}</tt>\n\nNo rules found for this device in /etc/udev/rules.d/")
        
        dialog.add_response("close", "Close")
        dialog.set_default_response("close")
        dialog.set_close_response("close")
        
        dialog.present()
    
    def on_apply_clicked(self, button):
        """Apply udev rules for selected devices - show device type selection first"""
        selected = self.get_selected_devices()
        if not selected:
            self.show_toast("No devices selected", error=True)
            return
        
        # Build list of device names
        device_list = []
        for device in selected:
            name = f"{device.vendor_name or 'Unknown'} {device.product_name or 'Device'}"
            vid_pid = f"[{device.vendor_id}:{device.product_id}]"
            device_list.append(f"• {name} {vid_pid}")
        
        # Create device type selection dialog
        dialog = Adw.Window(transient_for=self)
        dialog.set_modal(True)
        dialog.set_default_size(500, 450)
        dialog.set_title("Configure Device Rules")
        
        # Main content box
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        content.set_margin_top(24)
        content.set_margin_bottom(24)
        content.set_margin_start(24)
        content.set_margin_end(24)
        
        # Header
        header = Gtk.Label()
        header.set_markup(f"<b>Create rules for {len(selected)} device(s)</b>")
        header.set_halign(Gtk.Align.START)
        content.append(header)
        
        # Device list preview (scrollable)
        device_frame = Gtk.Frame()
        device_frame.set_margin_bottom(8)
        device_scroll = Gtk.ScrolledWindow()
        device_scroll.set_max_content_height(100)
        device_scroll.set_propagate_natural_height(True)
        device_label = Gtk.Label(label="\n".join(device_list[:8]))
        if len(device_list) > 8:
            device_label.set_text(device_label.get_text() + f"\n... and {len(device_list) - 8} more")
        device_label.set_halign(Gtk.Align.START)
        device_label.set_margin_top(8)
        device_label.set_margin_bottom(8)
        device_label.set_margin_start(12)
        device_scroll.set_child(device_label)
        device_frame.set_child(device_scroll)
        content.append(device_frame)
        
        # Device type selection
        type_label = Gtk.Label()
        type_label.set_markup("<b>Device Type Preset:</b>")
        type_label.set_halign(Gtk.Align.START)
        content.append(type_label)
        
        # Dropdown for device type
        type_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        preset_dropdown = Gtk.DropDown()
        preset_names = Gtk.StringList()
        preset_keys = list(DEVICE_PRESETS.keys())
        for key in preset_keys:
            preset_names.append(DEVICE_PRESETS[key]["name"])
        preset_dropdown.set_model(preset_names)
        preset_dropdown.set_selected(0)  # Default to first (controller)
        preset_dropdown.set_hexpand(True)
        type_box.append(preset_dropdown)
        content.append(type_box)
        
        # Description label
        desc_label = Gtk.Label()
        desc_label.set_markup(f"<i>{DEVICE_PRESETS[preset_keys[0]]['description']}</i>")
        desc_label.set_halign(Gtk.Align.START)
        desc_label.set_wrap(True)
        desc_label.set_opacity(0.8)
        content.append(desc_label)
        
        # Update description when selection changes
        def on_preset_changed(dropdown, _pspec):
            idx = dropdown.get_selected()
            if idx < len(preset_keys):
                desc_label.set_markup(f"<i>{DEVICE_PRESETS[preset_keys[idx]]['description']}</i>")
        
        preset_dropdown.connect("notify::selected", on_preset_changed)
        
        # Access toggles section
        toggle_label = Gtk.Label()
        toggle_label.set_markup("<b>Access Settings:</b>")
        toggle_label.set_halign(Gtk.Align.START)
        toggle_label.set_margin_top(12)
        content.append(toggle_label)
        
        # Toggle switches
        toggle_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        
        webhid_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        webhid_switch = Gtk.Switch()
        webhid_switch.set_active(True)
        webhid_switch.set_valign(Gtk.Align.CENTER)
        webhid_label = Gtk.Label(label="WebHID Access (browser config tools)")
        webhid_label.set_halign(Gtk.Align.START)
        webhid_label.set_hexpand(True)
        webhid_row.append(webhid_label)
        webhid_row.append(webhid_switch)
        toggle_box.append(webhid_row)
        
        rawusb_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        rawusb_switch = Gtk.Switch()
        rawusb_switch.set_active(False)
        rawusb_switch.set_valign(Gtk.Align.CENTER)
        rawusb_label = Gtk.Label(label="Raw USB Access (libusb, firmware flash)")
        rawusb_label.set_halign(Gtk.Align.START)
        rawusb_label.set_hexpand(True)
        rawusb_row.append(rawusb_label)
        rawusb_row.append(rawusb_switch)
        toggle_box.append(rawusb_row)
        
        serial_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        serial_switch = Gtk.Switch()
        serial_switch.set_active(False)
        serial_switch.set_valign(Gtk.Align.CENTER)
        serial_label = Gtk.Label(label="Serial Port Access (ttyUSB, ttyACM)")
        serial_label.set_halign(Gtk.Align.START)
        serial_label.set_hexpand(True)
        serial_row.append(serial_label)
        serial_row.append(serial_switch)
        toggle_box.append(serial_row)
        
        content.append(toggle_box)
        
        # Update toggles when preset changes
        def sync_toggles_from_preset(dropdown, _pspec):
            idx = dropdown.get_selected()
            if idx < len(preset_keys):
                settings = DEVICE_PRESETS[preset_keys[idx]]["settings"]
                webhid_switch.set_active(settings.get("webhid_access", True))
                rawusb_switch.set_active(settings.get("raw_usb_access", False))
                serial_switch.set_active(settings.get("serial_access", False))
        
        preset_dropdown.connect("notify::selected", sync_toggles_from_preset)
        sync_toggles_from_preset(preset_dropdown, None)  # Initial sync
        
        # Buttons
        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        button_box.set_halign(Gtk.Align.END)
        button_box.set_margin_top(16)
        
        cancel_button = Gtk.Button(label="Cancel")
        cancel_button.connect("clicked", lambda btn: dialog.close())
        button_box.append(cancel_button)
        
        create_button = Gtk.Button(label="Create Rules")
        create_button.add_css_class("suggested-action")
        
        def on_create_clicked(btn):
            # Get selected preset
            idx = preset_dropdown.get_selected()
            preset_key = preset_keys[idx] if idx < len(preset_keys) else "generic"
            
            # Create profile with user overrides
            profile = DeviceProfile(
                device_type=preset_key,
                webhid_access=webhid_switch.get_active(),
                raw_usb_access=rawusb_switch.get_active(),
                serial_access=serial_switch.get_active()
            )
            
            dialog.close()
            self.apply_rules_with_profile(selected, profile, preset_key)
        
        create_button.connect("clicked", on_create_clicked)
        button_box.append(create_button)
        
        content.append(button_box)
        dialog.set_content(content)
        dialog.present()
    
    def on_apply_confirmed(self, dialog, response, selected_devices):
        """Handle confirmation dialog response"""
        if response != "apply":
            return
        
        self.set_loading(True)
        self.progress_bar.set_text("Creating rules...")
        
        # Build device IDs from selected devices
        device_ids = []
        device_names = []
        for device in selected_devices:
            if device.vendor_id and device.product_id:
                device_ids.append(f"{device.vendor_id}:{device.product_id}")
                name = f"{device.vendor_name or 'Unknown'} {device.product_name or 'Device'}"
                device_names.append(name)
        
        if not device_ids:
            self.show_toast("No valid devices selected", error=True)
            self.set_loading(False)
            return
        
        # Show what we're about to configure
        print(f"[GUI] Configuring {len(device_ids)} device(s): {', '.join(device_ids)}")
        
        def apply_thread():
            try:
                cli_tool = self.find_cli_tool()
                if not cli_tool:
                    GLib.idle_add(self.show_toast, "Could not find udev-autoconfig CLI tool", True)
                    GLib.idle_add(self.set_loading, False)
                    return
                
                # Determine how to run the CLI tool
                if os.geteuid() == 0:
                    # Already root, run directly
                    if cli_tool.endswith('.py'):
                        cmd = [sys.executable, cli_tool, '--devices'] + device_ids
                    else:
                        cmd = [cli_tool, '--devices'] + device_ids
                else:
                    # Use pkexec for privilege escalation
                    if cli_tool.endswith('.py'):
                        cmd = ['pkexec', sys.executable, cli_tool, '--devices'] + device_ids
                    else:
                        cmd = ['pkexec', cli_tool, '--devices'] + device_ids
                
                print(f"[GUI] Running command: {' '.join(cmd)}")
                
                GLib.idle_add(self.progress_bar.set_text, "Requesting admin privileges...")
                GLib.idle_add(self.progress_bar.set_fraction, 0.2)
                
                # Run the CLI tool with --devices to create rules for selected devices
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True
                )
                
                # Print CLI output for debugging
                if result.stdout:
                    print(f"[CLI stdout] {result.stdout}")
                if result.stderr:
                    print(f"[CLI stderr] {result.stderr}")
                
                GLib.idle_add(self.progress_bar.set_fraction, 1.0)
                
                if result.returncode == 0:
                    GLib.idle_add(self.show_toast, f"Rules created for {len(device_ids)} device(s)!")
                    GLib.idle_add(self.load_devices)  # Refresh the list
                elif result.returncode == 126:
                    # User cancelled pkexec authentication
                    GLib.idle_add(self.show_toast, "Authentication cancelled", True)
                else:
                    error_msg = result.stderr.strip() if result.stderr else result.stdout.strip() if result.stdout else f"Exit code: {result.returncode}"
                    GLib.idle_add(self.show_toast, f"Failed: {error_msg}", True)
                
            except FileNotFoundError:
                GLib.idle_add(self.show_toast, "pkexec not found. Please install polkit.", True)
            except Exception as e:
                GLib.idle_add(self.show_toast, f"Error: {e}", True)
            finally:
                GLib.idle_add(self.set_loading, False)
        
        thread = threading.Thread(target=apply_thread)
        thread.daemon = True
        thread.start()
    
    def apply_rules_with_profile(self, selected_devices, profile, preset_key):
        """Apply rules with specific device profile settings"""
        self.set_loading(True)
        self.progress_bar.set_text(f"Creating {preset_key} rules...")
        
        # Build device IDs from selected devices
        device_ids = []
        for device in selected_devices:
            if device.vendor_id and device.product_id:
                device_ids.append(f"{device.vendor_id}:{device.product_id}")
        
        if not device_ids:
            self.show_toast("No valid devices selected", error=True)
            self.set_loading(False)
            return
        
        print(f"[GUI] Creating {preset_key} rules for {len(device_ids)} device(s)")
        
        def apply_thread():
            try:
                cli_tool = self.find_cli_tool()
                if not cli_tool:
                    GLib.idle_add(self.show_toast, "Could not find udev-autoconfig CLI tool", True)
                    GLib.idle_add(self.set_loading, False)
                    return
                
                # Build CLI arguments with profile settings
                cli_args = ['--devices'] + device_ids
                cli_args += ['--type', preset_key]
                
                if profile.raw_usb_access:
                    cli_args.append('--raw-usb')
                if profile.serial_access:
                    cli_args.append('--serial')
                if not profile.webhid_access:
                    cli_args.append('--no-webhid')
                
                # Determine how to run the CLI tool
                if os.geteuid() == 0:
                    if cli_tool.endswith('.py'):
                        cmd = [sys.executable, cli_tool] + cli_args
                    else:
                        cmd = [cli_tool] + cli_args
                else:
                    if cli_tool.endswith('.py'):
                        cmd = ['pkexec', sys.executable, cli_tool] + cli_args
                    else:
                        cmd = ['pkexec', cli_tool] + cli_args
                
                print(f"[GUI] Running command: {' '.join(cmd)}")
                
                GLib.idle_add(self.progress_bar.set_text, "Requesting admin privileges...")
                GLib.idle_add(self.progress_bar.set_fraction, 0.2)
                
                result = subprocess.run(cmd, capture_output=True, text=True)
                
                if result.stdout:
                    print(f"[CLI stdout] {result.stdout}")
                if result.stderr:
                    print(f"[CLI stderr] {result.stderr}")
                
                GLib.idle_add(self.progress_bar.set_fraction, 1.0)
                
                if result.returncode == 0:
                    GLib.idle_add(self.show_toast, f"{preset_key.title()} rules created for {len(device_ids)} device(s)!")
                    GLib.idle_add(self.load_devices)  # Refresh the list
                elif result.returncode == 126:
                    GLib.idle_add(self.show_toast, "Authentication cancelled", True)
                else:
                    error_msg = result.stderr.strip() if result.stderr else f"Exit code: {result.returncode}"
                    GLib.idle_add(self.show_toast, f"Failed: {error_msg}", True)
                
            except FileNotFoundError:
                GLib.idle_add(self.show_toast, "pkexec not found. Please install polkit.", True)
            except Exception as e:
                GLib.idle_add(self.show_toast, f"Error: {e}", True)
            finally:
                GLib.idle_add(self.set_loading, False)
        
        thread = threading.Thread(target=apply_thread)
        thread.daemon = True
        thread.start()
    
    def on_remove_clicked(self, button):
        """Remove udev rules for selected devices"""
        selected = self.get_selected_devices()
        if not selected:
            self.show_toast("No devices selected", error=True)
            return
        
        # Filter to only configured devices
        existing = self.generator.get_existing_rules()
        configured_selected = []
        for device in selected:
            if device.vendor_id and device.product_id:
                vid = device.vendor_id.lower()
                pid = device.product_id.lower()
                if vid in existing and pid in existing.get(vid, []):
                    configured_selected.append(device)
        
        if not configured_selected:
            self.show_toast("No configured devices selected", error=True)
            return
        
        # Build list of device names for confirmation
        device_list = []
        for device in configured_selected:
            name = f"{device.vendor_name or 'Unknown'} {device.product_name or 'Device'}"
            vid_pid = f"[{device.vendor_id}:{device.product_id}]"
            device_list.append(f"• {name} {vid_pid}")
        
        # Confirm action with device list
        dialog = Adw.MessageDialog(transient_for=self)
        dialog.set_heading("Remove udev rules?")
        dialog.set_body_use_markup(True)
        
        body_text = f"This will <b>remove</b> udev rules for <b>{len(configured_selected)}</b> device(s):\n\n"
        body_text += "\n".join(device_list[:10])
        if len(device_list) > 10:
            body_text += f"\n... and {len(device_list) - 10} more"
        
        dialog.set_body(body_text)
        
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("remove", "Remove Rules")
        dialog.set_response_appearance("remove", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response("cancel")
        dialog.set_close_response("cancel")
        
        dialog.connect("response", self.on_remove_confirmed, configured_selected)
        dialog.present()
    
    def on_remove_confirmed(self, dialog, response, selected_devices):
        """Handle remove confirmation dialog response"""
        if response != "remove":
            return
        
        self.set_loading(True)
        self.progress_bar.set_text("Removing rules...")
        
        # Build device IDs
        device_ids = []
        for device in selected_devices:
            if device.vendor_id and device.product_id:
                device_ids.append(f"{device.vendor_id}:{device.product_id}")
        
        if not device_ids:
            self.show_toast("No valid devices selected", error=True)
            self.set_loading(False)
            return
        
        print(f"[GUI] Removing rules for {len(device_ids)} device(s): {', '.join(device_ids)}")
        
        def remove_thread():
            try:
                cli_tool = self.find_cli_tool()
                if not cli_tool:
                    GLib.idle_add(self.show_toast, "Could not find udev-autoconfig CLI tool", True)
                    GLib.idle_add(self.set_loading, False)
                    return
                
                # Determine how to run the CLI tool
                if os.geteuid() == 0:
                    if cli_tool.endswith('.py'):
                        cmd = [sys.executable, cli_tool, '--remove'] + device_ids
                    else:
                        cmd = [cli_tool, '--remove'] + device_ids
                else:
                    if cli_tool.endswith('.py'):
                        cmd = ['pkexec', sys.executable, cli_tool, '--remove'] + device_ids
                    else:
                        cmd = ['pkexec', cli_tool, '--remove'] + device_ids
                
                print(f"[GUI] Running command: {' '.join(cmd)}")
                
                GLib.idle_add(self.progress_bar.set_text, "Requesting admin privileges...")
                GLib.idle_add(self.progress_bar.set_fraction, 0.2)
                
                result = subprocess.run(cmd, capture_output=True, text=True)
                
                if result.stdout:
                    print(f"[CLI stdout] {result.stdout}")
                if result.stderr:
                    print(f"[CLI stderr] {result.stderr}")
                
                GLib.idle_add(self.progress_bar.set_fraction, 1.0)
                
                if result.returncode == 0:
                    GLib.idle_add(self.show_toast, f"Rules removed for {len(device_ids)} device(s)!")
                    GLib.idle_add(self.load_devices)
                elif result.returncode == 126:
                    GLib.idle_add(self.show_toast, "Authentication cancelled", True)
                else:
                    error_msg = result.stderr.strip() if result.stderr else result.stdout.strip() if result.stdout else f"Exit code: {result.returncode}"
                    GLib.idle_add(self.show_toast, f"Failed: {error_msg}", True)
                
            except FileNotFoundError:
                GLib.idle_add(self.show_toast, "pkexec not found. Please install polkit.", True)
            except Exception as e:
                GLib.idle_add(self.show_toast, f"Error: {e}", True)
            finally:
                GLib.idle_add(self.set_loading, False)
        
        thread = threading.Thread(target=remove_thread)
        thread.daemon = True
        thread.start()
    
    def set_loading(self, loading: bool):
        """Set loading state"""
        self.refresh_button.set_sensitive(not loading)
        self.apply_button.set_sensitive(not loading)
        self.remove_button.set_sensitive(not loading)
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
    
    def on_scan_rules_clicked(self, button):
        """Scan rules and display audit results"""
        # Clear existing results
        while child := self.audit_results_list.get_first_child():
            self.audit_results_list.remove(child)
        
        # Get filter text
        filter_query = self.audit_filter_entry.get_text().strip() or None
        
        # Run audit
        auditor = RulesAuditor()
        auditor.parse_rules()
        
        # Apply filter if provided
        if filter_query:
            query = filter_query.lower()
            filtered_entries = []
            for entry in auditor.entries:
                device_id = f"{entry.vendor_id}:{entry.product_id}" if entry.product_id else entry.vendor_id
                if query in device_id or query in entry.raw_line.lower():
                    filtered_entries.append(entry)
            auditor.entries = filtered_entries
        
        issues_found = False
        
        # Duplicates
        duplicates = auditor.find_duplicates()
        if duplicates:
            issues_found = True
            for device_id, entries in duplicates.items():
                issue_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
                issue_box.set_margin_top(8)
                issue_box.set_margin_bottom(8)
                issue_box.set_margin_start(12)
                issue_box.set_margin_end(12)
                
                header = Gtk.Label()
                header.set_markup(f"<b>⚠ DUPLICATE:</b> <tt>{device_id}</tt>")
                header.set_halign(Gtk.Align.START)
                header.add_css_class("warning")
                issue_box.append(header)
                
                for entry in entries:
                    loc = Gtk.Label(label=f"  → {entry.filepath.name}:{entry.line_number}")
                    loc.set_halign(Gtk.Align.START)
                    loc.set_opacity(0.7)
                    issue_box.append(loc)
                
                self.audit_results_list.append(issue_box)
                self.audit_results_list.append(Gtk.Separator())
        
        # Conflicts
        conflicts = auditor.find_conflicts()
        if conflicts:
            issues_found = True
            for device_id, entries in conflicts.items():
                issue_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
                issue_box.set_margin_top(8)
                issue_box.set_margin_bottom(8)
                issue_box.set_margin_start(12)
                issue_box.set_margin_end(12)
                
                header = Gtk.Label()
                header.set_markup(f"<b>✗ CONFLICT:</b> <tt>{device_id}</tt>")
                header.set_halign(Gtk.Align.START)
                header.add_css_class("error")
                issue_box.append(header)
                
                for entry in entries:
                    mode_str = f'MODE="{entry.mode}"' if entry.mode else ""
                    group_str = f'GROUP="{entry.group}"' if entry.group else ""
                    loc = Gtk.Label(label=f"  → {entry.filepath.name}: {mode_str} {group_str}")
                    loc.set_halign(Gtk.Align.START)
                    loc.set_opacity(0.7)
                    issue_box.append(loc)
                
                self.audit_results_list.append(issue_box)
                self.audit_results_list.append(Gtk.Separator())
        
        # Overlaps
        overlaps = auditor.find_overlaps()
        if overlaps:
            issues_found = True
            for vid, (vendor_entry, product_entries) in overlaps.items():
                issue_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
                issue_box.set_margin_top(8)
                issue_box.set_margin_bottom(8)
                issue_box.set_margin_start(12)
                issue_box.set_margin_end(12)
                
                header = Gtk.Label()
                header.set_markup(f"<b>ℹ OVERLAP:</b> Vendor <tt>{vid}</tt> covers {len(product_entries)} product rules")
                header.set_halign(Gtk.Align.START)
                issue_box.append(header)
                
                loc = Gtk.Label(label=f"  → Vendor rule: {vendor_entry.filepath.name}:{vendor_entry.line_number}")
                loc.set_halign(Gtk.Align.START)
                loc.set_opacity(0.7)
                issue_box.append(loc)
                
                self.audit_results_list.append(issue_box)
                self.audit_results_list.append(Gtk.Separator())
        
        # If no issues
        if not issues_found:
            success_label = Gtk.Label()
            if filter_query:
                success_label.set_markup(f"<b>✓ No issues found for '{GLib.markup_escape_text(filter_query)}'</b>")
            else:
                success_label.set_markup("<b>✓ No issues found!</b>")
            success_label.set_margin_top(32)
            success_label.set_margin_bottom(32)
            success_label.add_css_class("success")
            self.audit_results_list.append(success_label)
        
        # Summary
        summary = Gtk.Label()
        summary.set_markup(f"<i>Scanned rules, {len(auditor.entries)} {'matched' if filter_query else 'total'}</i>")
        summary.set_margin_top(12)
        summary.set_margin_bottom(8)
        summary.set_opacity(0.6)
        self.audit_results_list.append(summary)
        
        # Build plain text version for clipboard
        text_parts = ["=== udev-autoconfig Rules Audit ===\n"]
        if filter_query:
            text_parts.append(f"Filter: {filter_query}\n")
        text_parts.append("")
        
        for device_id, entries in duplicates.items():
            text_parts.append(f"⚠ DUPLICATE: {device_id}")
            for entry in entries:
                text_parts.append(f"  → {entry.filepath.name}:{entry.line_number}")
            text_parts.append("")
        
        for device_id, entries in conflicts.items():
            text_parts.append(f"✗ CONFLICT: {device_id}")
            for entry in entries:
                mode_str = f'MODE="{entry.mode}"' if entry.mode else ""
                group_str = f'GROUP="{entry.group}"' if entry.group else ""
                text_parts.append(f"  → {entry.filepath.name}: {mode_str} {group_str}")
            text_parts.append("")
        
        for vid, (vendor_entry, product_entries) in overlaps.items():
            text_parts.append(f"ℹ OVERLAP: Vendor {vid} covers {len(product_entries)} product rules")
            text_parts.append(f"  → Vendor rule: {vendor_entry.filepath.name}:{vendor_entry.line_number}")
            text_parts.append("")
        
        if not issues_found:
            text_parts.append("✓ No issues found!")
        
        text_parts.append(f"\nScanned {len(auditor.entries)} rules total.")
        
        self.audit_results_text = "\n".join(text_parts)
        self.copy_audit_button.set_sensitive(True)
        
        self.show_toast(f"Scan complete: {len(duplicates)} duplicates, {len(conflicts)} conflicts, {len(overlaps)} overlaps")
    
    def on_copy_audit_clicked(self, button):
        """Copy audit results to clipboard"""
        if not self.audit_results_text:
            self.show_toast("No audit results to copy", error=True)
            return
        
        clipboard = self.get_clipboard()
        clipboard.set(self.audit_results_text)
        self.show_toast("Audit results copied to clipboard!")


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
            version=getattr(udev_module, "__version__", "unknown"),
            developers=["USB Device Auto-Config Contributors"],
            copyright="© 2025 USB Device Auto-Config",
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
