// Copyright (c) 2020, IT-Geräte und IT-Lösungen wie Server, Rechner, Netzwerke und E-Mailserver sowie auch Backups, and contributors
// For license information, please see license.txt

frappe.ui.form.on('CalDav Account', {
	refresh: function (frm) {
		if (!frm.is_new()) {
			frm.add_custom_button('Calendars', function () { frm.trigger('fetch_calendars') }, __("Fetch"));
		}
	},
	fetch_calendars: function(frm){
		frappe.call({
			method: "ice.api.fetch_calendars",
			args : { 'data' : {
				"url" : frm.doc.url,
				"username" : frm.doc.username,
				"password" : frm.doc.password,
				"caldavaccount" : frm.doc.name
			   }
			},
			callback: function(response_json){
			   console.log(json);
			}
		 });
	}
});
