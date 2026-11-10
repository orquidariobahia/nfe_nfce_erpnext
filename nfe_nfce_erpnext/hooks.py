app_name = "nfe_nfce_erpnext"
app_title = "NFe NFCe for ERPNext"
app_publisher = "shirkit"
app_description = 'Library for handling "Nota Fiscal" for brazillian tax compliance.'
app_email = "shirkit@gmail.com"
app_license = "mpl-2.0"
# required_apps = []

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
app_include_css = ["/assets/nfe_nfce_erpnext/css/pos.css"]
app_include_js = ["/assets/nfe_nfce_erpnext/js/whatsapp_share.js"]

# include js, css files in header of web template
# web_include_css = "/assets/nfe_nfce_erpnext/css/nfe_nfce_erpnext.css"
# web_include_js = "/assets/nfe_nfce_erpnext/js/nfe_nfce_erpnext.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "nfe_nfce_erpnext/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
page_js = {"point-of-sale": "public/js/pos.js"}

# include js in doctype views
doctype_js = {
    "Sales Invoice": "public/js/doctype/sales_invoice.js",
    "POS Invoice": "public/js/doctype/sales_invoice.js",
    "Customer" : "public/js/doctype/customer.js",
    "Supplier" : "public/js/doctype/customer.js",
    "Item": "public/js/doctype/item.js",
}
fixtures = [
    {
        "doctype": "Client Script",
        "filters": [["module", "in", ("NFe NFCe for ERPNext")]],
    },
    {
        "doctype": "Print Format",
        "filters": [["module", "in", ("NFe NFCe for ERPNext")]],
    },
]
doctype_list_js = {"Item" : "public/js/list_view/item_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "nfe_nfce_erpnext/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "nfe_nfce_erpnext.utils.jinja_methods",
# 	"filters": "nfe_nfce_erpnext.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "nfe_nfce_erpnext.install.before_install"
# after_install = "nfe_nfce_erpnext.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "nfe_nfce_erpnext.uninstall.before_uninstall"
# after_uninstall = "nfe_nfce_erpnext.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "nfe_nfce_erpnext.utils.before_app_install"
# after_app_install = "nfe_nfce_erpnext.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "nfe_nfce_erpnext.utils.before_app_uninstall"
# after_app_uninstall = "nfe_nfce_erpnext.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "nfe_nfce_erpnext.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# DocType Class
# ---------------
# Override standard doctype classes

# override_doctype_class = {
# 	"ToDo": "custom_app.overrides.CustomToDo"
# }

# Document Events
# ---------------
# Hook on document methods and events

doc_events = {
    "POS Invoice": {
        #"on_change": "nfe_nfce_erpnext.api.updatePosInvoice",
        "on_submit": "nfe_nfce_erpnext.api.submitPosInvoice",
    },
    "Loyalty Point Entry": {
        "before_insert": "nfe_nfce_erpnext.api.beforeInsertLoyaltyPointEntry",
    },
    "Item Price": {
        "after_insert": "nfe_nfce_erpnext.api.afterSaveItemPrice",
        "on_update": "nfe_nfce_erpnext.api.afterSaveItemPrice",
    }
}

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"nfe_nfce_erpnext.tasks.all"
# 	],
# 	"daily": [
# 		"nfe_nfce_erpnext.tasks.daily"
# 	],
# 	"hourly": [
# 		"nfe_nfce_erpnext.tasks.hourly"
# 	],
# 	"weekly": [
# 		"nfe_nfce_erpnext.tasks.weekly"
# 	],
# 	"monthly": [
# 		"nfe_nfce_erpnext.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "nfe_nfce_erpnext.install.before_tests"

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "nfe_nfce_erpnext.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "nfe_nfce_erpnext.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["nfe_nfce_erpnext.utils.before_request"]
# after_request = ["nfe_nfce_erpnext.utils.after_request"]

# Job Events
# ----------
# before_job = ["nfe_nfce_erpnext.utils.before_job"]
# after_job = ["nfe_nfce_erpnext.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"nfe_nfce_erpnext.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }
