from pathlib import Path
from bs4 import BeautifulSoup, NavigableString, Comment
import re
import json

ROOT = Path.cwd()
FRONTEND = ROOT / "frontend"
REACT = ROOT / "react-frontend"
PAGES = REACT / "src" / "pages"
PAGES.mkdir(parents=True, exist_ok=True)

# --- NEW: Font Awesome CDN link that every generated page relies on
# (fa-solid / fa-regular icon classes need this or every icon renders blank) ---
FONT_AWESOME_LINK = '<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.2/css/all.min.css">'

PAGE_NAMES = {
    "index.html": "Home",
    "login-choice.html": "LoginChoice",
    "login.html": "Login",
    "stu-login.html": "StuLogin",
    "admin-login.html": "AdminLogin",
    "stu-register.html": "Register",
    "admin-register.html": "AdminRegister",
    "stu-dashboard.html": "StudentDashboard",
    "admin-dashboard.html": "AdminDashboard",
    "course.html": "CourseDetails",
    "courses.html": "Courses",
    "certificate.html": "Certificate",
    "add-course.html": "AddCourse",
    "add-course-edit.html": "AddCourseEdit",
    "edit-course.html": "EditCourse",
    "edit-course-login.html": "EditCourseLogin",
    "forget-password.html": "ForgotPassword",
    "reset-password.html": "ResetPassword",
    "notifications.html": "Notifications"
}

SCRIPT_NAMES = {
    "add-course.html": "add_course.js",
    "admin-dashboard.html": "admin_dashboard.js",
    "admin-register.html": "admin_register.js",
    "certificate.html": "certificate.js",
    "course.html": "course_details.js",
    "courses.html": "courses.js",
    "edit-course.html": "edit_course.js",
    "forget-password.html": "forgot_password.js",
    "login.html": "login.js",
    "reset-password.html": "reset_password.js",
    "stu-dashboard.html": "student_dashboard.js",
    "stu-register.html": "student_register.js"
}

ROUTES = {
    "index.html": "/",
    "login.html": "/login",
    "stu-register.html": "/register",
    "admin-register.html": "/admin-register",
    "stu-dashboard.html": "/dashboard",
    "admin-dashboard.html": "/admin-dashboard",
    "courses.html": "/courses",
    "course.html": "/course-details",
    "certificate.html": "/certificate",
    "forget-password.html": "/forgot-password",
    "reset-password.html": "/reset-password",
    "add-course.html": "/add-course",
    "edit-course.html": "/edit-course"
}

CSS_NAMES = {
    "index.html": "index.css",
    "login.html": "login.css",
    "stu-register.html": "student_register.css",
    "admin-register.html": "admin_register.css",
    "stu-dashboard.html": "student_dashboard.css",
    "admin-dashboard.html": "admin_dashboard.css",
    "courses.html": "courses.css",
    "course.html": "course_details.css",
    "certificate.html": "certificate.css",
    "add-course.html": "add_course.css",
    "edit-course.html": "edit_courses.css",
    "forget-password.html": "forgot_password.css",
    "reset-password.html": "reset_password.css",
    "notifications.html": "index.css"
}

VARIANTS = {
    "index.html": "home",
    "courses.html": "student",
    "stu-dashboard.html": "student",
    "course.html": "student3",
    "certificate.html": "cert",
    "add-course.html": "admin",
    "edit-course.html": "admin",
    "admin-dashboard.html": "adminnone"
}

VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
ATTRIBUTE_MAP = {"class": "className", "for": "htmlFor", "tabindex": "tabIndex", "readonly": "readOnly", "maxlength": "maxLength", "minlength": "minLength", "autocomplete": "autoComplete", "colspan": "colSpan", "rowspan": "rowSpan"}

# --- NEW: track pages that contain JS-toggled show/hide patterns (modals, overlays, etc.)
# so we can warn the user they need manual React state instead of a plain 1:1 conversion. ---
NEEDS_MANUAL_REVIEW = []
OVERLAY_CLASS_HINTS = ("overlay", "modal", "popup", "dropdown", "toast", "tooltip")


def quote(value):
    return json.dumps(str(value), ensure_ascii=False)


def convert_style(value):
    if not isinstance(value, str):
        return "{}"
    properties = []
    for item in value.split(";"):
        if ":" not in item:
            continue
        key, val = item.split(":", 1)
        key, val = key.strip(), val.strip()
        if not key:
            continue
        key = re.sub(r"-([a-z])", lambda match: match.group(1).upper(), key)
        properties.append(f"{key}: {quote(val)}")
    return "{" + ", ".join(properties) + "}"


def convert_text(value):
    value = str(value)
    value = value.replace("{", "{'{' }")
    value = value.replace("}", "{'}' }")
    return value.strip()


def convert_attributes(tag):
    attributes = []
    for key, value in tag.attrs.items():
        if key == "style":
            attributes.append(f"style={{{convert_style(value)}}}")
            continue
        if key.startswith("on") and isinstance(value, str):
            event_name = key[2:].capitalize()
            attributes.append(f'on{event_name}={{() => window.eval({quote(value)})}}')
            continue
        new_key = ATTRIBUTE_MAP.get(key, key)
        if isinstance(value, list):
            value = " ".join(value)
        if value is None or value == key:
            attributes.append(new_key)
            continue
        attributes.append(f"{new_key}={quote(value)}")
    return "" if not attributes else " " + " ".join(attributes)


def check_overlay_hint(tag, page_name):
    """NEW: flag elements whose class suggests they're shown/hidden via a JS-toggled
    class (e.g. '.enroll-modal-overlay.active'). A 1:1 static conversion will render
    these using CSS that expects that class, but nothing in the converted JSX ever
    adds it -> the element silently stays invisible. These pages need a manual
    useState-driven rewrite, same as Courses.jsx needed for the enroll modal."""
    class_list = tag.attrs.get("class") if getattr(tag, "attrs", None) else None
    if not class_list:
        return
    if isinstance(class_list, list):
        class_text = " ".join(class_list).lower()
    else:
        class_text = str(class_list).lower()
    if any(hint in class_text for hint in OVERLAY_CLASS_HINTS):
        entry = (page_name, class_text)
        if entry not in NEEDS_MANUAL_REVIEW:
            NEEDS_MANUAL_REVIEW.append(entry)


def convert_node(node, level=0, page_name=""):
    indent = "    " * level
    if isinstance(node, Comment):
        return indent + "{/* " + str(node).strip() + " */}"
    if isinstance(node, NavigableString):
        text_value = convert_text(node)
        if not text_value:
            return ""
        return indent + text_value
    if not getattr(node, "name", None) or node.name in ("script", "style"):
        return ""

    check_overlay_hint(node, page_name)

    if node.name == "a":
        href = node.get("href")
        route = ROUTES.get(href)
        if route:
            attrs = []
            for key, value in node.attrs.items():
                if key == "href":
                    continue
                if key == "style":
                    attrs.append(f"style={{{convert_style(value)}}}")
                    continue
                if key.startswith("on") and isinstance(value, str):
                    event_name = key[2:].capitalize()
                    attrs.append(f'on{event_name}={{() => window.eval({quote(value)})}}')
                    continue
                new_key = ATTRIBUTE_MAP.get(key, key)
                if isinstance(value, list):
                    value = " ".join(value)
                attrs.append(f"{new_key}={quote(value)}")
            attribute_text = " " + " ".join(attrs) if attrs else ""
            children = []
            for child in node.children:
                converted = convert_node(child, level + 1, page_name)
                if converted:
                    children.append(converted)
            if not children:
                return indent + f'<Link to={quote(route)}{attribute_text}></Link>'
            return indent + f'<Link to={quote(route)}{attribute_text}>\n' + "\n".join(children) + "\n" + indent + "</Link>"

    tag_name = node.name
    attribute_text = convert_attributes(node)
    if tag_name in VOID_TAGS:
        return indent + f"<{tag_name}{attribute_text} />"
    children = []
    for child in node.children:
        converted = convert_node(child, level + 1, page_name)
        if converted:
            children.append(converted)
    if not children:
        return indent + f"<{tag_name}{attribute_text}></{tag_name}>"
    if len(children) == 1 and not children[0].lstrip().startswith("<") and "\n" not in children[0]:
        return indent + f"<{tag_name}{attribute_text}>" + children[0].lstrip() + f"</{tag_name}>"
    return indent + f"<{tag_name}{attribute_text}>\n" + "\n".join(children) + "\n" + indent + f"</{tag_name}>"


def ensure_font_awesome():
    """NEW: make sure react-frontend/index.html always has Font Awesome loaded.
    Without this every fa-solid/fa-regular icon in every generated page renders
    as a blank box (this was the cause of the missing course logos / edit icon)."""
    index_html = REACT / "index.html"
    if not index_html.exists():
        print(f"WARNING: {index_html} not found, skipping Font Awesome injection.")
        return
    html = index_html.read_text(encoding="utf-8")
    if "font-awesome" in html.lower() or "fontawesome" in html.lower():
        return  # already present
    if "</head>" in html:
        html = html.replace("</head>", f"    {FONT_AWESOME_LINK}\n</head>")
    else:
        html = FONT_AWESOME_LINK + "\n" + html
    index_html.write_text(html, encoding="utf-8")
    print(f"Patched: {index_html} (added Font Awesome link)")


for html_file in FRONTEND.glob("*.html"):
    page_name = html_file.name
    component_name = PAGE_NAMES.get(page_name)
    if not component_name:
        continue
    html = html_file.read_text(encoding="utf-8")
    soup = BeautifulSoup(html, "html.parser")
    body = soup.body
    if body is None:
        continue
    header = body.find("header")
    footer = body.find("footer")
    has_header = header is not None
    has_footer = footer is not None
    if header:
        header.decompose()
    if footer:
        footer.decompose()
    content = []
    for child in body.children:
        converted = convert_node(child, 3, page_name)
        if converted:
            content.append(converted)
    content_text = "\n".join(content)
    imports = [
        'import PageCss from "../components/PageCss";',
        'import LegacyScript from "../components/LegacyScript";'
    ]
    if "<Link " in content_text:
        imports.insert(0, 'import { Link } from "react-router-dom";')
    if has_header or has_footer:
        imports.insert(0, 'import PageShell from "../components/PageShell";')
    variant = VARIANTS.get(page_name, "none")
    if has_header or has_footer:
        wrapped_content = f'<PageShell variant="{variant}">\n' + content_text + "\n            </PageShell>"
    else:
        wrapped_content = content_text
    css_file = CSS_NAMES.get(page_name, "index.css")
    script_file = SCRIPT_NAMES.get(page_name)
    if script_file:
        if script_file == "login.js":
            script_component = '<LegacyScript src="/legacy/js/login.js" module={true} />'
        else:
            script_component = f'<LegacyScript src="/legacy/js/{script_file}" />'
    else:
        script_component = ""
    component_code = "\n".join(imports) + "\n\n" + f"export default function {component_name}() {{\n" + "    return (\n" + "        <>\n" + f'            <PageCss href="/css/{css_file}" />\n' + "            " + wrapped_content + "\n            " + script_component + "\n" + "        </>\n" + "    );\n" + "}\n"
    output_file = PAGES / f"{component_name}.jsx"
    output_file.write_text(component_code, encoding="utf-8")
    print("Created:", output_file)

# --- NEW: patch index.html once, after all pages are generated ---
ensure_font_awesome()

print()
if NEEDS_MANUAL_REVIEW:
    print("=" * 60)
    print("MANUAL REVIEW NEEDED:")
    print("These pages have elements whose visibility depends on a JS-toggled")
    print("class (e.g. '.overlay.active'). The generated JSX is a static 1:1")
    print("copy and will NOT show/hide them correctly on its own -- you need to")
    print("rewrite them with useState, the way Courses.jsx's enroll modal was:")
    print("=" * 60)
    for page_name, class_text in NEEDS_MANUAL_REVIEW:
        print(f"  - {page_name}: class=\"{class_text}\"")
    print()

print("React page conversion completed.")
