frappe.ui.form.on('iCalendar', {
	refresh: function (frm) {
		if (!frm.is_new()) {
			frm.add_custom_button('Calendar', function () { frm.trigger('sync_calendar') }, __("Sync"));
		}
	},
	sync_calendar: function(frm){
		frappe.msgprint({
			title: __('Notification'),
			message: __('Sync might take some time. Are you sure you want to proceed?'),
			primary_action:{
				action(values) {
					frappe.call({
						method: "ice.api.sync_calendar",
						args : { 'data' : {
							"caldavaccount" : frm.doc.caldav_account,
							"calendarurl" : frm.doc.calendar_url,
							"caldavcalendar" : frm.doc.name,
							"color" : frm.doc.color
						   }
						},
						callback: function(response_json){
						   var r = JSON.parse(response_json.message)
						   console.log(r)
						}
					 });
				}
			}
		});
		
	}
});