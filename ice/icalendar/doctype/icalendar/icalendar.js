frappe.ui.form.on('iCalendar', {
	refresh: function (frm) {
		if (!frm.is_new()) {
			frm.add_custom_button('Download', function () { frm.trigger('download_calendar') }, __("Sync"));
			frm.add_custom_button('Upload', function () { frm.trigger('upload_calendar') }, __("Sync"));
		}
	},
	default_icalendar_of_user: function(frm){
		//Check if the User is set in another iCalendar
		frm.disable_save();
		frappe.call({
			method: 'frappe.client.get_list',
			args: {
				doctype: 'iCalendar',
				fields: ['name','default_icalendar_of_user'],
				page_length: 20000
			},
			callback: function(data){
				let e = data.message;
				for (let i = 0; i < e.length; i++) {
					const default_user = e[i]["default_icalendar_of_user"];
					if(frm.doc.default_icalendar_of_user == default_user){
						frappe.msgprint('The iCalendar <b>' + e[i]["name"] + '</b> has the User <b>' + frm.doc.default_icalendar_of_user + '</b> set as default. Only one default possible per user.');
						frm.set_value('default_icalendar_of_user', '')
						break;
					}
				}
				frm.enable_save();
			}
		});
	},
	download_calendar: function(frm){
		frappe.call({
			method: "ice.api.download_calendar",
			args : { 'data' : {
				"caldavaccount" : frm.doc.caldav_account,
				"calendarurl" : frm.doc.calendar_url,
				"icalendar" : frm.doc.name,
				"color" : frm.doc.color
				}
			},
			callback: function(response_json){
				var r = JSON.parse(response_json.message)
				console.log(r)
				//show_alert with indicator
				frappe.show_alert({
					message:__('iCalendar Download complete.'),
					indicator:'green'
				}, 7);
			}
		});
		frappe.msgprint(__('iCalendar Download started...'));
	},
	upload_calendar: function(frm){
		frappe.call({
			method: "ice.api.upload_calendar",
			args : { 'data' : {
				"caldavaccount" : frm.doc.caldav_account,
				"calendarurl" : frm.doc.calendar_url,
				"icalendar" : frm.doc.name
				}
			},
			callback: function(response_json){
				var r = JSON.parse(response_json.message)
				console.log(r)
				//show_alert with indicator
				frappe.show_alert({
					message:__('iCalendar Upload complete.'),
					indicator:'green'
				}, 7);
			}
		});
		frappe.msgprint(__('iCalendar Upload started...'));
	}
});
