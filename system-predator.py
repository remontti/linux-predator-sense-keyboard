import gi
import psutil
import math
import cairo
import time
import platform
from pynvml import *

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, GLib, Gdk, Pango, PangoCairo

def get_neon_thermal(p):
    p = max(0.0, min(1.0, p))
    if p < 0.5:
        f = p * 2
        return 0.11 + f * 0.85, 0.84 - f * 0.08, 0.49 - f * 0.42
    else:
        f = (p - 0.5) * 2
        return 0.96, 0.76 - f * 0.65, 0.07 + f * 0.07

# --- VETORES ANIMADOS ---
def draw_icon_cpu(cr, x, y, t):
    cr.save()
    cr.translate(x, y)
    cr.set_line_width(1.5)
    cr.set_source_rgb(0.6, 0.6, 0.6)
    cr.rectangle(-8, -8, 16, 16)
    cr.stroke()
    for i in [-4, 0, 4]:
        cr.move_to(-10, i); cr.line_to(-8, i)
        cr.move_to(8, i); cr.line_to(10, i)
        cr.move_to(i, -10); cr.line_to(i, -8)
        cr.move_to(i, 8); cr.line_to(i, 10)
    cr.stroke()
    pulse = (math.sin(t * 4) + 1) / 2
    cr.set_source_rgba(0.2, 0.9, 0.4, 0.3 + pulse * 0.7)
    cr.rectangle(-3, -3, 6, 6)
    cr.fill()
    cr.restore()

def draw_icon_gpu(cr, x, y, t):
    cr.save()
    cr.translate(x, y)
    cr.set_line_width(1.5)
    cr.set_source_rgb(0.6, 0.6, 0.6)
    cr.rectangle(-10, -6, 20, 12)
    cr.stroke()
    cr.move_to(10, -2); cr.line_to(13, -2)
    cr.move_to(10, 2); cr.line_to(13, 2)
    cr.stroke()
    cr.translate(-3, 0)
    cr.rotate(t * 8)
    cr.set_source_rgb(1.0, 0.2, 0.2)
    cr.move_to(-3, 0); cr.line_to(3, 0)
    cr.move_to(0, -3); cr.line_to(0, 3)
    cr.stroke()
    cr.restore()

def draw_icon_ram(cr, x, y, t):
    cr.save()
    cr.translate(x, y)
    cr.set_line_width(1.5)
    cr.set_source_rgb(0.6, 0.6, 0.6)
    cr.rectangle(-10, -4, 20, 8)
    cr.stroke()
    for i in [-6, 0, 6]:
        pulse = (math.sin(t * 5 + i) + 1) / 2
        cr.set_source_rgba(0.0, 0.8, 1.0, 0.2 + pulse * 0.8)
        cr.rectangle(i - 2, -2, 4, 4)
        cr.fill()
    cr.restore()

def draw_icon_fan(cr, x, y, rpm, t):
    cr.save()
    cr.translate(x, y)
    speed = (rpm / 4900) * 25
    cr.rotate(t * speed)
    if rpm < 2000: cr.set_source_rgb(0.0, 0.8, 1.0)
    elif rpm < 4000: cr.set_source_rgb(1.0, 0.8, 0.0)
    else: cr.set_source_rgb(1.0, 0.2, 0.2)
    
    for _ in range(3):
        cr.rotate(math.pi * 2 / 3)
        cr.move_to(0, 0)
        cr.curve_to(5, -5, 8, -8, 2, -10)
        cr.line_to(0, 0)
        cr.fill()
    cr.restore()

def draw_icon_disk(cr, x, y, t):
    cr.save()
    cr.translate(x, y)
    cr.set_line_width(1.5)
    cr.set_source_rgb(0.6, 0.6, 0.6)
    cr.arc(0, 0, 7, 0, 2 * math.pi)
    cr.stroke()
    cr.arc(0, 0, 2, 0, 2 * math.pi)
    cr.stroke()
    pulse = (math.sin(t * 3) + 1) / 2
    cr.set_source_rgba(1.0, 0.4, 0.0, 0.3 + pulse * 0.7)
    cr.arc(0, 0, 1.5, 0, 2 * math.pi)
    cr.fill()
    cr.restore()

def draw_icon_battery(cr, x, y, t):
    cr.save()
    cr.translate(x, y)
    cr.set_line_width(1.5)
    cr.set_source_rgb(0.6, 0.6, 0.6)
    cr.rectangle(-10, -5, 18, 10)
    cr.stroke()
    cr.rectangle(8, -2, 2, 4)
    cr.fill()
    pulse = (math.sin(t * 2) + 1) / 2
    cr.set_source_rgba(0.2, 0.9, 0.4, 0.3 + pulse * 0.7)
    cr.rectangle(-8, -3, 14, 6)
    cr.fill()
    cr.restore()

# --- WIDGETS ---
class PremiumGauge(Gtk.DrawingArea):
    def __init__(self, label, min_v=0, max_v=100, icon_type='cpu', is_large=False):
        super().__init__()
        self.label = label
        self.min_v, self.max_v = min_v, max_v
        self.icon_type = icon_type
        self.val = 0
        self.markup_txt = "0"
        self.sub_label = ""
        self.set_content_height(220 if is_large else 180)
        self.set_hexpand(True)
        self.set_draw_func(self.draw, None)

    def set_val(self, v, markup_txt, sub_label=""):
        self.val = max(self.min_v, min(self.max_v, v))
        self.markup_txt = markup_txt
        self.sub_label = sub_label

    def draw(self, area, cr, w, h, data):
        t = time.time()
        xc, yc = w / 2, h * 0.60 
        radius = min(w, h) * 0.45
        cr.set_line_width(20)
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        
        # Fundo do arco
        cr.set_source_rgba(0.15, 0.15, 0.18, 0.8)
        cr.arc(xc, yc, radius, math.pi, 2 * math.pi)
        cr.stroke()

        # Progresso
        p = (self.val - self.min_v) / (self.max_v - self.min_v)
        if p > 0:
            r, g, b = get_neon_thermal(p)
            cr.set_source_rgb(r, g, b)
            cr.arc(xc, yc, radius, math.pi, math.pi + (p * math.pi))
            cr.stroke()

        # Texto Principal (com Pango Markup para fontes de tamanhos diferentes na mesma linha)
        cr.set_source_rgb(1, 1, 1)
        l = self.create_pango_layout("")
        l.set_markup(self.markup_txt)
        tw, th = l.get_pixel_size()
        cr.move_to(xc - tw/2, yc - th + 5)
        PangoCairo.show_layout(cr, l)

        # Ícone Animado
        icon_y = yc + 20
        if self.icon_type == 'cpu': draw_icon_cpu(cr, xc, icon_y, t)
        elif self.icon_type == 'gpu': draw_icon_gpu(cr, xc, icon_y, t)
        elif self.icon_type == 'disk': draw_icon_disk(cr, xc, icon_y, t)
        elif self.icon_type == 'battery': draw_icon_battery(cr, xc, icon_y, t)
        else: draw_icon_ram(cr, xc, icon_y, t)

        # Label Limpo em baixo do ícone
        cr.set_source_rgb(0.6, 0.6, 0.65)
        sl = self.create_pango_layout(self.label)
        sl.set_font_description(Pango.FontDescription.from_string("Cantarell Bold 10"))
        sw, sh = sl.get_pixel_size()
        cr.move_to(xc - sw/2, icon_y + 12)
        PangoCairo.show_layout(cr, sl)

        if self.sub_label:
            cr.set_source_rgb(0.8, 0.8, 0.8)
            ssl = self.create_pango_layout("")
            ssl.set_markup(self.sub_label)
            ssw, ssh = ssl.get_pixel_size()
            cr.move_to(xc - ssw/2, icon_y + 28)
            PangoCairo.show_layout(cr, ssl)

class FanTacometer(Gtk.DrawingArea):
    def __init__(self):
        super().__init__()
        self.rpm = 0
        self.set_content_height(80)
        self.set_hexpand(True)
        self.set_draw_func(self.draw, None)

    def set_rpm(self, v):
        self.rpm = v

    def draw(self, area, cr, w, h, data):
        t = time.time()
        leds = 24
        sp = 5
        lw = min(8, (w - (leds * sp)) / leds)
        total_w = leds * (lw + sp)
        start_x = (w - total_w) / 2
        
        active = min(leds, int((self.rpm / 4900) * leds))
        
        if self.rpm < 2000: active_c = (0.0, 0.8, 1.0)
        elif self.rpm < 4000: active_c = (1.0, 0.8, 0.0)
        else: active_c = (1.0, 0.1, 0.2)
        
        for i in range(leds):
            x = start_x + i * (lw + sp)
            if i < active:
                cr.set_source_rgb(*active_c)
            else:
                cr.set_source_rgba(0.2, 0.2, 0.25, 0.4) 
            
            cr.set_line_width(lw)
            cr.set_line_cap(cairo.LINE_CAP_ROUND)
            cr.move_to(x + lw/2, 20)
            cr.line_to(x + lw/2, h - 35)
            cr.stroke()
        
        # Hélice girando + Apenas o RPM
        draw_icon_fan(cr, start_x + 20, h - 16, self.rpm, t)
        
        cr.set_source_rgb(*active_c)
        l = self.create_pango_layout(f"{self.rpm} RPM")
        l.set_font_description(Pango.FontDescription.from_string("Cantarell Bold 11"))
        cr.move_to(start_x + 36, h - 24)
        PangoCairo.show_layout(cr, l)

class StatusLedBar(Gtk.DrawingArea):
    def __init__(self, icon_type='disk'):
        super().__init__()
        self.icon_type = icon_type
        self.percent = 0
        self.markup_txt = ""
        self.set_content_height(80)
        self.set_hexpand(True)
        self.set_draw_func(self.draw, None)

    def set_val(self, percent, markup_txt):
        self.percent = max(0, min(100, percent))
        self.markup_txt = markup_txt

    def draw(self, area, cr, w, h, data):
        t = time.time()
        leds = 30
        sp = 4
        lw = min(8, (w - (leds * sp)) / leds)
        total_w = leds * (lw + sp)
        start_x = (w - total_w) / 2
        
        active = min(leds, int((self.percent / 100) * leds))
        p_active = self.percent / 100
        
        for i in range(leds):
            x = start_x + i * (lw + sp)
            if i < active:
                if self.icon_type == 'battery':
                    if p_active < 0.2: cr.set_source_rgb(1.0, 0.1, 0.2)
                    elif p_active < 0.5: cr.set_source_rgb(1.0, 0.8, 0.0)
                    else: cr.set_source_rgb(0.2, 0.9, 0.4)
                else: # disk
                    if p_active < 0.7: cr.set_source_rgb(0.0, 0.8, 1.0)
                    elif p_active < 0.9: cr.set_source_rgb(1.0, 0.8, 0.0)
                    else: cr.set_source_rgb(1.0, 0.1, 0.2)
            else:
                cr.set_source_rgba(0.2, 0.2, 0.25, 0.4) 
            
            cr.set_line_width(lw)
            cr.set_line_cap(cairo.LINE_CAP_ROUND)
            cr.move_to(x + lw/2, 20)
            cr.line_to(x + lw/2, h - 35)
            cr.stroke()
        
        # Icon
        if self.icon_type == 'disk': draw_icon_disk(cr, start_x + 20, h - 16, t)
        else: draw_icon_battery(cr, start_x + 20, h - 16, t)
        
        cr.set_source_rgb(0.8, 0.8, 0.8)
        l = self.create_pango_layout("")
        l.set_markup(self.markup_txt)
        l.set_font_description(Pango.FontDescription.from_string("Cantarell Bold 11"))
        cr.move_to(start_x + 36, h - 24)
        PangoCairo.show_layout(cr, l)


class PowerBadge(Gtk.DrawingArea):
    def __init__(self):
        super().__init__()
        self.mode = "Unknown"
        self.set_content_height(80)
        self.set_hexpand(True)
        self.set_draw_func(self.draw, None)

    def set_mode(self, mode):
        self.mode = mode

    def draw(self, area, cr, w, h, data):
        c_r, c_g, c_b = 0.6, 0.6, 0.6
        if self.mode == "Performance": c_r, c_g, c_b = 1.0, 0.2, 0.2
        elif self.mode == "Balanced": c_r, c_g, c_b = 0.0, 0.8, 1.0
        elif self.mode == "Power Saver": c_r, c_g, c_b = 0.2, 0.9, 0.4
            
        xc, yc = w / 2, h / 2
        bw, bh = 340, 50
        
        # Background
        cr.set_source_rgba(0.12, 0.12, 0.14, 0.8)
        self._rounded_rect(cr, xc - bw/2, yc - bh/2, bw, bh, bh/2)
        cr.fill()
        
        # Pulse Dot
        pulse = (math.sin(time.time() * 4) + 1) / 2 if self.mode == "Performance" else 1.0
        cr.set_source_rgba(c_r, c_g, c_b, 0.2 + pulse * 0.4)
        cr.arc(xc - bw/2 + 30, yc, 10, 0, 2*math.pi)
        cr.fill()
        
        cr.set_source_rgb(c_r, c_g, c_b)
        cr.arc(xc - bw/2 + 30, yc, 5, 0, 2*math.pi)
        cr.fill()
        
        hex_c = "#{:02x}{:02x}{:02x}".format(int(c_r*255), int(c_g*255), int(c_b*255))
        cr.set_source_rgb(1, 1, 1)
        l = self.create_pango_layout("")
        l.set_markup(f"<span font='Cantarell Bold 12' color='#aaaaaa'>SYSTEM POWER: </span><span font='Cantarell Bold 12' color='{hex_c}'>{self.mode.upper()}</span>")
        tw, th = l.get_pixel_size()
        cr.move_to(xc - bw/2 + 55, yc - th/2)
        PangoCairo.show_layout(cr, l)
        
    def _rounded_rect(self, cr, x, y, width, height, radius):
        cr.arc(x + width - radius, y + radius, radius, -math.pi/2, 0)
        cr.arc(x + width - radius, y + height - radius, radius, 0, math.pi/2)
        cr.arc(x + radius, y + height - radius, radius, math.pi/2, math.pi)
        cr.arc(x + radius, y + radius, radius, math.pi, 3*math.pi/2)
        cr.close_path()

class SysInfoBar(Gtk.DrawingArea):
    def __init__(self):
        super().__init__()
        self.os = ""
        self.kernel = ""
        self.uptime = ""
        self.set_content_height(80)
        self.set_hexpand(True)
        self.set_draw_func(self.draw, None)
        
    def set_data(self, os_n, kernel, up):
        self.os, self.kernel, self.uptime = os_n, kernel, up
        
    def draw(self, area, cr, w, h, data):
        cw = min(280, (w - 40) / 3)
        ch = 56
        start_x = (w - (3 * cw + 40)) / 2
        
        items = [
            ("OS", self.os, (0.0, 0.82, 1.0)),
            ("KERNEL", self.kernel, (1.0, 0.8, 0.0)),
            ("UPTIME", self.uptime, (0.0, 1.0, 0.5))
        ]
        
        for i, (title, val, col) in enumerate(items):
            x = start_x + i * (cw + 20)
            yc = h / 2
            
            cr.set_source_rgba(0.12, 0.12, 0.14, 0.8)
            radius = 12
            cr.arc(x + cw - radius, yc - ch/2 + radius, radius, -math.pi/2, 0)
            cr.arc(x + cw - radius, yc + ch/2 - radius, radius, 0, math.pi/2)
            cr.arc(x + radius, yc + ch/2 - radius, radius, math.pi/2, math.pi)
            cr.arc(x + radius, yc - ch/2 + radius, radius, math.pi, 3*math.pi/2)
            cr.close_path()
            cr.fill()
            
            cr.set_source_rgb(*col)
            cr.rectangle(x, yc - ch/2 + 15, 4, ch - 30)
            cr.fill()
            
            hex_c = "#{:02x}{:02x}{:02x}".format(int(col[0]*255), int(col[1]*255), int(col[2]*255))
            l = self.create_pango_layout("")
            l.set_markup(f"<span font='Cantarell Bold 10' color='{hex_c}'>{title}</span>\n<span font='Cantarell 11' color='#eeeeee'>{val}</span>")
            cr.move_to(x + 15, yc - 20)
            PangoCairo.show_layout(cr, l)


class MonitorApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id='com.remontti.predator.dash')
        try:
            nvmlInit()
            self.gpu_h = nvmlDeviceGetHandleByIndex(0)
            self.has_gpu = True
        except: self.has_gpu = False

    def get_power_mode(self):
        import subprocess
        try:
            mode = subprocess.check_output(['powerprofilesctl', 'get'], text=True, stderr=subprocess.DEVNULL).strip()
            if mode == "performance": return "Performance"
            if mode == "balanced": return "Balanced"
            if mode == "power-saver": return "Power Saver"
            return mode.capitalize()
        except:
            try:
                with open("/sys/firmware/acpi/platform_profile", "r") as f:
                    return f.read().strip().capitalize()
            except:
                return "Auto/Unknown"

    def get_sys_info_data(self):
        uptime = int(time.time() - psutil.boot_time())
        h = uptime // 3600
        m = (uptime % 3600) // 60
        os_name = "Linux"
        try:
            with open("/etc/os-release") as f:
                for line in f:
                    if line.startswith("PRETTY_NAME="):
                        os_name = line.split("=")[1].strip().strip('"')
        except: pass
        if "GNU/Linux" in os_name: os_name = os_name.replace("GNU/Linux", "").strip()
        os_name = os_name.replace("  ", " ")
        
        return os_name, platform.release() if 'platform' in globals() else 'Unknown', f"{h}h {m}m"

    def do_activate(self):
        Adw.StyleManager.get_default().set_color_scheme(Adw.ColorScheme.FORCE_DARK)
        
        win = Adw.ApplicationWindow(application=self)
        win.set_title("Predator Analytics")
        win.set_default_size(950, 1150) 
        
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

        tview = Adw.ToolbarView()
        tview.add_top_bar(Adw.HeaderBar())
        win.set_content(tview)

        css = Gtk.CssProvider()
        css.load_from_data("window { background-color: #181818; }", -1)
        win.get_style_context().add_provider_for_display(Gdk.Display.get_default(), css, 800)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=45)
        box.set_margin_start(50); box.set_margin_end(50)
        box.set_margin_top(30); box.set_margin_bottom(40)
        
        scroll.set_child(box)
        tview.set_content(scroll)

        # 0. System Info Bar
        self.sys_bar = SysInfoBar()
        box.append(self.sys_bar)

        # 1. CPU / GPU
        grid_top = Gtk.Grid(column_spacing=30, column_homogeneous=True)
        box.append(grid_top)
        
        self.cpu_g = PremiumGauge("ULTRA 9 PROCESSOR", icon_type='cpu', is_large=True)
        grid_top.attach(self.cpu_g, 0, 0, 1, 1)
        
        if self.has_gpu:
            self.gpu_g = PremiumGauge("RTX 5070 GRAPHICS", icon_type='gpu', is_large=True)
            grid_top.attach(self.gpu_g, 1, 0, 1, 1)

        # 2. FANS
        self.fan_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=25, homogeneous=True)
        box.append(self.fan_box)
        self.fan_widgets = {}

        # 3. RAM / VRAM / SWAP
        mem_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=25, homogeneous=True)
        box.append(mem_box)
        
        self.ram_g = PremiumGauge("RAM", icon_type='ram')
        self.vram_g = PremiumGauge("VRAM", icon_type='ram')
        self.swap_g = PremiumGauge("SWAP", icon_type='ram')
        mem_box.append(self.ram_g); mem_box.append(self.vram_g); mem_box.append(self.swap_g)

        # 3.5 DISK e BATTERY
        extra_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=25, homogeneous=True)
        box.append(extra_box)
        
        self.disk_g = StatusLedBar(icon_type='disk')
        self.bat_g = StatusLedBar(icon_type='battery')
        extra_box.append(self.disk_g); extra_box.append(self.bat_g)

        # 4. POWER BADGE
        self.pm_badge = PowerBadge()
        box.append(self.pm_badge)

        # Loops
        GLib.timeout_add(500, self.update_data)
        GLib.timeout_add(30, self.animate_ui)
        win.present()

    def get_highest_temp(self):
        try:
            temps = psutil.sensors_temperatures()
            high = 0
            if 'coretemp' in temps:
                for entry in temps['coretemp']:
                    if 'Package' in entry.label: return entry.current
                    if entry.current > high: high = entry.current
                if high > 0: return high
            
            if 'acer_isa' in temps:
                for entry in temps['acer_isa']:
                    if entry.current > high: high = entry.current
                if high > 0: return high
            
            for k, v in temps.items():
                for entry in v:
                    if entry.current > high: high = entry.current
            return high if high > 0 else 0
        except:
            return 0

    def update_data(self):
        if not hasattr(self, 'sys_update_loop') or self.sys_update_loop % 20 == 0:
            os_n, krnl, up = self.get_sys_info_data()
            self.sys_bar.set_data(os_n, krnl, up)
            self.pm_badge.set_mode(self.get_power_mode())
            self.sys_update_loop = 0
        self.sys_update_loop += 1

        # CPU
        cpu_p = psutil.cpu_percent()
        cpu_t = self.get_highest_temp()
        t_color = "#ff4444" if cpu_t > 85 else "#00d2ff"
        self.cpu_g.set_val(cpu_p, f"<span font='36'>{int(cpu_p)}</span><span font='16' color='#aaaaaa'> %</span>", f"<span color='{t_color}' font='14'>🌡️ {int(cpu_t)}°C</span>" if cpu_t else "")
        
        # GPU
        if self.has_gpu:
            gpu_p = nvmlDeviceGetUtilizationRates(self.gpu_h).gpu
            try: gpu_t = nvmlDeviceGetTemperature(self.gpu_h, NVML_TEMPERATURE_GPU)
            except: gpu_t = 0
            gt_color = "#ff4444" if gpu_t > 80 else "#00d2ff"
            self.gpu_g.set_val(gpu_p, f"<span font='36'>{int(gpu_p)}</span><span font='16' color='#aaaaaa'> %</span>", f"<span color='{gt_color}' font='14'>🌡️ {int(gpu_t)}°C</span>" if gpu_t else "")
            
            m = nvmlDeviceGetMemoryInfo(self.gpu_h)
            v_u = m.used / (1024**3)
            v_t = m.total / (1024**3)
            v_p = (m.used / m.total) * 100
            self.vram_g.set_val(v_p, f"<span font='28'>{v_u:.1f}</span><span font='12' color='#aaaaaa'> / {v_t:.0f} GB</span>")

        # RAM & SWAP
        r = psutil.virtual_memory()
        r_u = r.used / (1024**3)
        r_t = r.total / (1024**3)
        self.ram_g.set_val(r.percent, f"<span font='28'>{r_u:.1f}</span><span font='12' color='#aaaaaa'> / {r_t:.0f} GB</span>")
        
        s = psutil.swap_memory()
        self.swap_g.set_val(s.percent, f"<span font='28'>{s.percent}</span><span font='12' color='#aaaaaa'> %</span>")

        # DISK & BATTERY
        disk = psutil.disk_usage('/')
        d_u = disk.used / (1024**3)
        d_t = disk.total / (1024**3)
        self.disk_g.set_val(disk.percent, f"<b>DISK</b>   <span color='#aaaaaa'>{d_u:.0f} / {d_t:.0f} GB</span>")
        
        bat = psutil.sensors_battery()
        if bat:
            b_s = "Plugged" if bat.power_plugged else f"{int(bat.secsleft/60)} min" if bat.secsleft != psutil.POWER_TIME_UNKNOWN else "Unplugged"
            self.bat_g.set_val(bat.percent, f"<b>BATT</b>   <span color='#aaaaaa'>{int(bat.percent)}%  |  {b_s}</span>")
        else:
            self.bat_g.set_val(100, f"<b>BATT</b>   <span color='#aaaaaa'>AC</span>")

        # FANS (Sem labels inúteis, apenas RPM)
        fans = psutil.sensors_fans()
        for name, entries in fans.items():
            for i, entry in enumerate(entries):
                key = f"{name}_{i}"
                if key not in self.fan_widgets:
                    tacho = FanTacometer()
                    self.fan_box.append(tacho)
                    self.fan_widgets[key] = tacho
                self.fan_widgets[key].set_rpm(entry.current)

        return True

    def animate_ui(self):
        self.cpu_g.queue_draw()
        if self.has_gpu: self.gpu_g.queue_draw()
        self.ram_g.queue_draw(); self.vram_g.queue_draw(); self.swap_g.queue_draw()
        self.disk_g.queue_draw(); self.bat_g.queue_draw()
        for fan in self.fan_widgets.values(): fan.queue_draw()
        self.pm_badge.queue_draw()
        self.sys_bar.queue_draw()
        return True

if __name__ == '__main__':
    app = MonitorApp()
    app.run(None)
