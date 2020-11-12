from __future__ import unicode_literals
from frappe import _


def get_data():
    return [
        {
            "label": _("Calendar"),
            "items": [
                {
                    "type": "doctype",
                    "name": "iCalendar",
                    "label": _("iCalendar"),
                    "description": _("Main calendar management doctype")
                },
                {
                    "type": "doctype",
                    "name": "Event",
                    "label": _("Event"),
                    "description": _("Event")
                },
                {
                    "type": "doctype",
                    "name": "Custom Pattern",
                    "label": _("Custom Pattern"),
                    "description": _("Custom Pattern")
                },
                {
                    "type": "doctype",
                    "name": "CalDav Account",
                    "label": _("CalDav Account"),
                    "description": _("CalDav Account Settings")
                },
            ],
        },
        {
            "label": _("Settings"),
            "items":[
                {
                    "type": "doctype",
                    "name": "iCalendar Settings",
                    "label": _("iCalendar Settings"),
                    "description": _("Settingspage for general Settings")
                },
            ]
        }
    ]