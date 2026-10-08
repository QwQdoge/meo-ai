from gi.repository import Gtk, Pango

class TodoListWidget(Gtk.Box):
    """Modern todo list widget with interactive checkboxes"""
    
    def __init__(self, todos: list, on_toggle_callback=None, title: str = "Tasks"):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add_css_class("card")
        self.set_size_request(-1, 200)
        self.set_margin_top(8)
        self.set_margin_bottom(8)
        
        self.on_toggle = on_toggle_callback
        
        # Custom CSS
        css_provider = Gtk.CssProvider()
        css_provider.load_from_data(b"""
            .todo-header {
                padding: 12px 16px;
                background: alpha(@accent_bg_color, 0.08);
            }
            .todo-item {
                padding: 8px 16px;
                border-bottom: 1px solid alpha(@borders, 0.3);
            }
            .todo-item:last-child {
                border-bottom: none;
            }
            .todo-completed .todo-text {
                text-decoration: line-through;
                opacity: 0.5;
            }
            .phase-header {
                background: alpha(@view_bg_color, 0.5);
                padding: 6px 16px;
                font-weight: 600;
                font-size: 12px;
            }
        """)
        Gtk.StyleContext.add_provider_for_display(
            self.get_display(),
            css_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
        
        # Convert todos format: 'status' -> 'completed', 'title' -> 'text'
        converted_todos = []
        for todo in todos:
            status = todo.get("status", "not-started")
            completed = status == "completed"
            converted_todos.append({
                'text': todo.get('title', 'No title'),
                'completed': completed,
                'phase': todo.get('phase', 'Other')
            })
        
        completed_count = sum(1 for t in converted_todos if t.get('completed', False))
        total = len(converted_todos)
        
        # Header
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        header.add_css_class("todo-header")
        
        icon = Gtk.Image.new_from_icon_name("checkbox-checked-symbolic")
        icon.set_pixel_size(18)
        icon.add_css_class("accent")
        header.append(icon)
        
        title_label = Gtk.Label(label=title, xalign=0, hexpand=True)
        title_label.add_css_class("heading")
        header.append(title_label)
        
        count_label = Gtk.Label(label=f"{completed_count}/{total}")
        count_label.add_css_class("caption")
        count_label.add_css_class("dim-label")
        header.append(count_label)
        
        self.append(header)
        
        # Group by phase
        phases = {}
        for todo in converted_todos:
            phase = todo.get('phase', 'Other')
            if phase not in phases:
                phases[phase] = []
            phases[phase].append(todo)
        
        # Create todo items
        list_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        
        for phase, phase_todos in phases.items():
            if len(phases) > 1 and phase:
                # Phase header
                phase_header = Gtk.Label(label=phase, xalign=0)
                phase_header.add_css_class("phase-header")
                list_box.append(phase_header)
            
            for todo in phase_todos:
                row = self._create_todo_row(todo)
                list_box.append(row)
        
        # Scrolled container for long lists
        if len(converted_todos) > 5:
            scrolled = Gtk.ScrolledWindow()
            scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
            scrolled.set_max_content_height(300)
            scrolled.set_propagate_natural_height(True)
            scrolled.set_child(list_box)
            self.append(scrolled)
        else:
            self.append(list_box)
    
    def _create_todo_row(self, todo: dict) -> Gtk.Box:
        """Create a single todo item row"""
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        row.add_css_class("todo-item")
        if todo.get('completed'):
            row.add_css_class("todo-completed")
        
        # Checkbox
        check = Gtk.CheckButton()
        check.set_active(todo.get('completed', False))
        check.set_valign(Gtk.Align.CENTER)
        check.set_sensitive(False)
        if self.on_toggle:
            check.connect("toggled", lambda btn, txt=todo.get('text', ''): self.on_toggle(txt, btn.get_active()))
        row.append(check)
        
        # Text
        text_label = Gtk.Label(
            label=todo.get('text', ''),
            xalign=0,
            hexpand=True,
            wrap=True,
            wrap_mode=Pango.WrapMode.WORD_CHAR,
        )
        text_label.add_css_class("todo-text")
        row.append(text_label)
        
        return row
