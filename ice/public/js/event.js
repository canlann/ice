frappe.ui.form.on('Event', {
    // on refresh event
    refresh(frm) {
        
    },
    validate(frm) {

        //Validate the Event Type
        if(!(["Public","Private","Confidential","Cancelled"].includes(frm.doc.event_type))){
            frappe.throw(__('If you want to synchronize this event the ') + __('Event Type') + __(' must be one of ') + __('Public') + ", " + __('Private') + ", " + __('Confidential') + " or " + __('Cancelled'))
        }

        //If Doc is new => Add metadata for syncing
        if(frm.is_new()){
            frm.set_value("created_on", frappe.datetime.get_datetime_as_string())
        }
        
        frm.set_value("last_modified", frappe.datetime.get_datetime_as_string())

        //Set Default Calendar by User
        
    }
});