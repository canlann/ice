import frappe
import sys


## We'll try to use the local caldav library, not the system-installed
sys.path.insert(0, '..')

from frappe.utils.dateutils import *
import caldav
from ice.caldav_utils import *
import json
import datetime
import dateutil
import dateutil.rrule as RR
import vobject
import traceback

@frappe.whitelist()
def fetch_calendars(data):
    #Check if called from client side (not necessary)
    if(isinstance(data,str)):
        data = json.loads(data)

    account = frappe.get_doc("CalDav Account",data["caldavaccount"])

    client = caldav.DAVClient(url=data["url"], username=data["username"], password=data["password"])
    principal = client.principal()
    calendars = principal.calendars()

    for calendar in calendars:
        #Check if Calendar exists already

        #If not create
        doc = frappe.new_doc("iCalendar")
        doc.title = cleanName(calendar.name)
        doc.caldav_account = data["caldavaccount"]
        doc.calendar_url = str(calendar)
        #doc.parent = data["caldavaccount"]
        #doc.parentfield = "calendars"
        #doc.parenttype = "CalDav Account"
        doc.insert()

        doc.link = cleanName(calendar.name)

        account.append('icalendars',{
            'icalendar': doc.name
        })
        account.save()
        doc.save()
    
    print("Done")
    
    return "response"

@frappe.whitelist()
def download_calendar(data):
    #UI Progress Display
    percent_progress = 0
    frappe.show_progress('Downloading..', percent_progress, 100, 'Please wait');

    #Constants
    sync_period = 90


    #Check if called from client side (not necessary)
    if(isinstance(data,str)):
        data = json.loads(data)

    #Connect to CalDav Account
    account = frappe.get_doc("CalDav Account", data["caldavaccount"])
    """
    account = data["caldavaccount"]
    """
    client = caldav.DAVClient(url=account.url, username=account.username, password=account.password)
    principal = client.principal()
    calendars = principal.calendars()

    #Look for the right calendar
    for calendar in calendars:
        if(str(calendar) == data["calendarurl"]):
            cal = calendar
    
    #Go through Events
    events = cal.events()

    #Stats
    stats = {
        "1a" : 0,
        "1b" : 0,
        "1c" : 0,
        "2a" : 0,
        "3a" : 0,
        "3b" : 0,
        "4a" : 0,
        "else" : 0,
        "error" : 0,
        "not_inserted" : 0,
        "exception_block_standard" : 0,
        "exception_block_meta" : 0
    }
    rstats = {
        "norrule" : 0,
        "daily" : 0,
        "weekly" : 0,
        "monthly" : 0,
        "yearly" : 0,
        "finite" : 0,
        "infinite" : 0,
        "total" : len(events),
        "singular_event" :0,
        "error" : 0,
        "exception" :0
    }
    #Error Stack
    error_stack = []

    for idx,event in enumerate(events):
        vev = event.vobject_instance.vevent
        
        #By default an event is not insertable in ERP
        insertable = False

        try:
            #Following conversion makes it Timezone naive!
            if(hasattr(vev,"dtstart") and type(vev.dtstart.value) is datetime.date):
                value = vev.dtstart.value
                dtstart = datetime.datetime(value.year,value.month,value.day)
            elif(hasattr(vev,"dtstart")):
                dtstart = vev.dtstart.value
            else:
                dtstart = None

            if(hasattr(vev,"dtend") and type(vev.dtend.value) is datetime.date):
                value = vev.dtend.value
                dtend = datetime.datetime(value.year,value.month,value.day)
            elif(hasattr(vev,"dtend")):
                dtend = vev.dtend.value
            else:
                dtend = None

            #Berechne Dinge
            if(hasattr(vev,"dtstart") and hasattr(vev,"dtend")):
                timedelta = dtend - dtstart
                days = (dtend.date() - dtstart.date()).days
            elif(hasattr(vev,"dtstart") and hasattr(vev,"duration")):
                timedelta = vev.duration.value #Real time difference
                days = ((dtstart + vev.duration.value).date() - dtstart.date()).days #Full days between the dates 0,1,2...

            #Standard Fields
            doc = frappe.new_doc("Event")
            """
            doc = DotMap()
            """
            if(vev.summary.value == "WG"):
                vev.prettyPrint()

            doc.subject = vev.summary.value
            doc.starts_on = dtstart.strftime("%Y-%m-%d %H:%M:%S")
            if(hasattr(vev,"description")):
                doc.description = vev.description.value
            doc.event_type = vev.__getattr__("class").value.title()
            
            #Case 1a: has dtend, within a day
            if((hasattr(vev,"dtend") and days == 0)):
                doc.ends_on = dtend.strftime("%Y-%m-%d %H:%M:%S")
                insertable = True
                stats["1a"] += 1
            #Case 1b: has duration, within a day
            elif(hasattr(vev,"duration") and days == 0 ):
                doc.ends_on = (dtstart + vev.duration.value).strftime("%Y-%m-%d %H:%M:%S")
                insertable = True
                stats["1b"] += 1
            #Case 1c: Allday, one day
            elif( timedelta.days == 1 and timedelta.seconds == 0 and dtstart.hour == 0 and dtstart.minute == 0):
                doc.ends_on = ""
                doc.all_day = 1
                insertable = True
                stats["1c"] += 1
            #Case 2a: Allday, more than one day
            elif(timedelta.days >= 1 and timedelta.seconds == 0):
                doc.ends_on = (dtstart + timedelta).strftime("%Y-%m-%d %H:%M:%S")
                doc.all_day = 1
                insertable = True
                stats["2a"] += 1
            #Case 3a: has dtend, not within a day
            elif((hasattr(vev,"dtend") and days >= 1)):
                doc.ends_on = (dtstart + timedelta).strftime("%Y-%m-%d %H:%M:%S")
                insertable = True
                stats["3a"] += 1
            #Case 3b: has duration, not within a day
            elif((hasattr(vev,"duration") and days > 0)):
                doc.ends_on = (dtstart + timedelta).strftime("%Y-%m-%d %H:%M:%S")
                insertable = True
                stats["3b"] += 1
            #Case else: ( ATM: No dtend, No Duration,...)
            else:
                stats["else"] += 1
            
        except Exception as ex:
            #traceback.print_exc()
            tb = traceback.format_exc()
            insertable = False
            stats["exception_block_standard"] += 1
            error_stack.append({ "message" : "Problem with Standard Fields/Cases. Exception: \n" + tb, "icalendar" : vev.serialize()})

        #If the event has a recurrence rule this will be handled here, by default rrules are not mappable to ERP
        mapped = False
        try:
            #RRULE CONVERSION
            if(hasattr(vev,"rrule")):
                rule = dateutil.rrule.rrulestr(vev.rrule.value,dtstart=vev.dtstart.value)
                
                #Include only mappable rrules
                if(isMappable(vev,rule)):
                    #DAILY
                    if(rule._freq == 3 and noByDay(vev.rrule.value)):
                        doc.repeat_this_event = 1
                        doc.repeat_on = "Daily"
                        until = getUntil(vev.dtstart.value,rule)
                        if until:
                            doc.repeat_till = until.strftime("%Y-%m-%d")
                        mapped = True
                        rstats["daily"] += 1
                    #DAILY to WEEKLY (Special Case SP1)
                    elif(rule._freq == 3 and not noByDay(vev.rrule.value)):
                        match = re.search(r'BY[A-Z]{4,5}DAY',vev.rrule.value) #Catches BYWEEKDAY, BYMONTHDAY and BYYEARDAY
                        if match:
                            print("Special Case not applicable")
                            rstats["error"] += 1
                            error_stack.append({ "message" : "Daily SP1 not applicable", "icalendar" : vev.serialize()})
                        else:
                            doc.repeat_this_event = 1
                            doc.repeat_on = "Weekly"
                            until = getUntil(vev.dtstart.value,rule)
                            if until:
                                doc.repeat_till = until.strftime("%Y-%m-%d")
                            if 0 in rule._byweekday:
                                doc.monday = 1
                            if 1 in rule._byweekday:
                                doc.tuesday = 1
                            if 2 in rule._byweekday:
                                doc.wednesday = 1
                            if 3 in rule._byweekday:
                                doc.thursday = 1
                            if 4 in rule._byweekday:
                                doc.friday = 1
                            if 5 in rule._byweekday:
                                doc.saturday = 1
                            if 6 in rule._byweekday:
                                doc.sunday = 1
                            mapped = True
                            rstats["weekly"] += 1
                    #WEEKLY
                    elif(rule._freq == 2):
                        doc.repeat_this_event = 1
                        doc.repeat_on = "Weekly"
                        until = getUntil(vev.dtstart.value,rule)
                        if until:
                            doc.repeat_till = until.strftime("%Y-%m-%d")
                        if 0 in rule._byweekday:
                            doc.monday = 1
                        if 1 in rule._byweekday:
                            doc.tuesday = 1
                        if 2 in rule._byweekday:
                            doc.wednesday = 1
                        if 3 in rule._byweekday:
                            doc.thursday = 1
                        if 4 in rule._byweekday:
                            doc.friday = 1
                        if 5 in rule._byweekday:
                            doc.saturday = 1
                        if 6 in rule._byweekday:
                            doc.sunday = 1
                        mapped = True
                        rstats["weekly"] += 1
                    #MONTHLY
                    elif(rule._freq == 1 and noByDay(vev.rrule.value) and isNotFebruaryException(vev.dtstart.value.date())):
                        doc.repeat_this_event = 1
                        doc.repeat_on = "Monthly"
                        until = getUntil(vev.dtstart.value,rule)
                        if until:
                            doc.repeat_till = until.strftime("%Y-%m-%d")
                        mapped = True
                        rstats["monthly"] += 1
                    #YEARLY
                    elif(rule._freq == 0 and noByDay(vev.rrule.value) and isNotFebruaryException(vev.dtstart.value.date())):
                        doc.repeat_this_event = 1
                        doc.repeat_on = "Yearly"
                        until = getUntil(vev.dtstart.value,rule)
                        if until:
                            doc.repeat_till = until.strftime("%Y-%m-%d")
                        mapped = True
                        rstats["yearly"] += 1
                    #Not mapped
                    else:
                        rstats["error"] += 1
                        error_stack.append({ "message" : "Mappable but Not mapped", "icalendar" : vev.serialize()})
                
            else:
                mapped = True
                rstats["norrule"] += 1
        
        except Exception as ex:
            #traceback.print_exc()
            tb = traceback.format_exc()
            mapped = False
            rstats["exception"] += 1
            error_stack.append({ "message" : "RRule mapping error. Exception: \n" + tb, "icalendar" : vev.serialize()})


        try:
            #Specials: Metafields
            if(hasattr(vev,"transp")):
                if(vev.transp.value == "TRANSPARENT"):
                    doc.color = color_variant(data["color"])
                elif(vev.transp.value == "OPAQUE"):
                    doc.color = data["color"]
            else:
                doc.color = data["color"]

            if(hasattr(vev,"status")):
                #print("Status: " + vev.status.value)
                pass
            if(hasattr(vev,"organizer")):
                #print("Organizer: " + vev.organizer.value)
                pass
            if(hasattr(vev,"attendee")):
                #vev.prettyPrint()
                pass
            if(hasattr(vev, "sequence")):
                #print("Sequence: " + vev.sequence.value)
                pass
            if(hasattr(vev,"location")):
                #print("Location: " + vev.location.value)
                pass
            
            #ICalendar Meta Information for Sync
            if(hasattr(vev,"last_modified")):
                doc.last_modified = vev.last_modified.value.strftime("%Y-%m-%d %H:%M:%S")
            if(hasattr(vev,"created")):
                doc.created_on = vev.created.value.strftime("%Y-%m-%d %H:%M:%S")
            if(hasattr(vev,"uid")):
                doc.uid = vev.uid.value
            else:
                raise Exception('Exception:', 'Event has no UID')
            doc.icalendar = data["icalendar"]
        
            #Insert
            if(insertable and mapped):
                """
                """
                doc.insert(
                        ignore_permissions=False, # ignore write permissions during insert
                        ignore_links=True, # ignore Link validation in the document
                        ignore_if_duplicate=True, # dont insert if DuplicateEntryError is thrown
                        ignore_mandatory=False # insert even if mandatory fields are not set
                )
            #Has rrule, not mappable to Custom Pattern
            elif(hasattr(vev,"rrule")):
                #Finite Event
                is_finite = False
                if(re.search(r'UNTIL|COUNT',vev.rrule.value)):
                    #vev.prettyPrint()
                    datetimes = list(vev.getrruleset())
                    is_finite = True
                    rstats["finite"] += 1
                #Infinite Event
                else:
                    #vev.prettyPrint()
                    vev.rrule.value = vev.rrule.value + ";UNTIL=" + (datetime.datetime.now() + datetime.timedelta(days=sync_period)).strftime("%Y%m%d")
                    datetimes = list(vev.getrruleset())
                    rstats["infinite"] += 1

                #Does not need a Custom Pattern
                if(len(datetimes) == 1):
                    """
                    """
                    doc.insert() #TODO Remeber this is a strange case too, cause it has a rrule but only one event
                    rstats["singular_event"] += 1
                #Create Custom Pattern and Linked Events
                else:
                    """
                    cp = DotMap()
                    """
                    cp = frappe.new_doc("Custom Pattern")
                    cp.title = vev.summary.value
                    cp.icalendar = data["icalendar"]
                    if(hasattr(vev,"created")):
                        cp.created_on = vev.created.value.strftime("%Y-%m-%d %H:%M:%S")
                    if(hasattr(vev,"last_modified")):
                        cp.last_modified = vev.last_modified.value.strftime("%Y-%m-%d %H:%M:%S")
                    if(hasattr(vev,"uid")):
                        cp.uid = vev.uid.value
                    else:
                        raise Exception("Exception:", "Event has no UID")
                    if(is_finite):
                        cp.duration = "Finite"
                    else:
                        cp.duration = "Infinite"

                    cp.newest_event_on = datetimes[len(datetimes)-1].strftime("%Y-%m-%d %H:%M:%S")
                    
                    """
                    """
                    cp.insert()

                    for dt_starts_on in datetimes:
                        """
                        event = DotMap()
                        """
                        event = frappe.new_doc("Event")
                        event.subject = vev.summary.value
                        event.starts_on = dt_starts_on.strftime("%Y-%m-%d %H:%M:%S")
                        #In ERP Allday Events should have an empty field for ends_on -> dtendtime = None
                        if(doc.ends_on == "" or doc.ends_on is None):
                            event.ends_on = ""
                        else:
                            dtendtime = datetime.datetime.strptime(doc.ends_on, "%Y-%m-%d %H:%M:%S").time()
                            event.ends_on = dt_starts_on.strftime("%Y-%m-%d") + " " + dtendtime.strftime("%H:%M:%S")
                        event.type = vev.__getattr__("class").value.title()
                        if(hasattr(vev,"transp")):
                            if(vev.transp.value == "TRANSPARENT"):
                                event.color = color_variant(data["color"])
                            elif(vev.transp.value == "OPAQUE"):
                                event.color = data["color"]
                        else:
                            event.color = data["color"]

                        if(hasattr(vev,"description")):
                            description = vev.description.value
                        else:
                            description = None

                        event.repeat_this_event = 1
                        
                        """
                        """
                        event.custom_pattern = cp.name
                        event.insert()
                        cp.append('events', {
                                'event' : event.name
                        })
                    cp.save()
                    """
                    """

                    #print(datetimes)
                    #print("CP created.")
            
            #Has no rrule, not mappable and strange for unknown reason
            else:
                stats["not_inserted"] += 1
        
        except Exception as ex:
            #traceback.print_exc()
            tb = traceback.format_exc()
            stats["exception_block_meta"] += 1
            error_stack.append({ "message" : "Problem with Meta fields or doc insertion. Exception: \n" + tb, "icalendar" : vev.serialize()})

        #Update UI
        percent_progress = idx / len(events) * 100
        frappe.publish_progress(percent=percent_progress, title="Downloading")
            
            
 
    #Return JSON and Log
    message = {}
    message["stats"] = stats
    message["rstats"] = rstats
    message["error_stack"] = error_stack

    """
    """

    d = frappe.get_doc("iCalendar", data["icalendar"])
    d.last_sync_log = json.dumps(message)
    d.save()
    d.add_comment('Comment',text="Stats:\n" + str(stats) + "\nRRule Stats:\n" + str(rstats))

    """
    """

    return json.dumps(message)

@frappe.whitelist()
def upload_calendar(data):
    #Check if called from client side (not necessary)
    if(isinstance(data,str)):
        data = json.loads(data)

    #Connect to CalDav Account
    account = frappe.get_doc("CalDav Account", data["caldavaccount"])
    """
    account = data["caldavaccount"]
    """
    client = caldav.DAVClient(url=account.url, username=account.username, password=account.password)
    principal = client.principal()
    calendars = principal.calendars()

    #Look for the right calendar
    for calendar in calendars:
        if(str(calendar) == data["calendarurl"]):
            cal = calendar
    
    #Go through events
    erp_events = frappe.db.sql("""
        SELECT
            *
        FROM `tabEvent`
        WHERE icalendar = '{icalendar}' AND custom_pattern is NULL;
    """.format(icalendar = data["icalendar"]),as_dict=1)


    weekdays = ["monday","tuesday","wednesday","thursday","friday","saturday","sunday"]
    rrweekdays = [RR.MO,RR.TU,RR.WE,RR.TH,RR.FR,RR.SA,RR.SU]

    upstats = {
        "10a" : 0,
        "10b" : 0,
        "10c" : 0,
        "11b" : 0,
        "not_uploadable" :0,
        "exceptions" : 0,
    }

    rstats = {
        "mapped" : 0,
        "not_mapped" :0,
    }
    #Error Stack
    error_stack = []

    for idx,ee in enumerate(erp_events):
        uploadable = True
        try:
            print(ee)
            #Case 10a: Status Open, everything nominal
            if(ee["status"] == "Open"):
                new_calendar = vobject.newFromBehavior('vcalendar')
                e  = new_calendar.add('vevent')
                e.add('summary').value = ee["subject"]
                dtstart = ee["starts_on"]
                e.add('dtstart').value = dtstart
                e.add('description').value = ee["description"]
                if(ee["event_type"] in ["Public","Private","Confidential"]):
                    e.add('class').value = ee["event_type"]
                #Case 10b: Status Open, but Event Type is Cancelled
                elif(ee["event_type"] == "Cancelled"):
                    print(ee["event_type"])
                    uploadable = False
                    upstats["10b"] += 1
                #Case 10c: Status Open, but Event Type not in [Public, Private, Confidential,Cancelled]
                else:
                    print(ee["event_type"])
                    uploadable = False
                    upstats["10c"] += 1
                dtend = ee["ends_on"]
                if(dtend == None):
                        dtend = dtstart + datetime.timedelta(minutes=15)
                        frappe.db.set_value('Event', ee["name"], 'ends_on', dtend, update_modified=False)
                if(ee["all_day"] == 0):
                    e.add('dtend').value = dtend
                else:
                    e.dtstart.value = dtstart.date()
                    dtend = (dtend.date() + datetime.timedelta(days=1))
                    e.add('dtend').value = dtend

                if(ee["last_modified"] == None):
                    frappe.db.set_value('Event', ee["name"], 'last_modified', ee["modified"].replace(microsecond=0), update_modified=False)
                    e.add('last-modified').value = ee["modified"].replace(microsecond=0)
                else:
                    e.add('last-modified').value = ee["last_modified"]

                if(ee["created_on"] == None):
                    frappe.db.set_value('Event', ee["name"], 'created_on', ee["creation"].replace(microsecond=0), update_modified=False)
                    e.add('created').value = ee["creation"].replace(microsecond=0)
                else:
                    e.add('created').value = ee["created_on"]

                #Create rrule
                rrule = None
                until = ee["repeat_till"]
                byweekday = []
                if(ee["repeat_this_event"] == 1 and ee["repeat_till"] != None):
                    until = datetime.datetime(until.year,until.month,until.day,dtstart.hour,dtstart.minute,dtstart.second)
                if(ee["repeat_on"] == "Daily"):
                    rrule = RR.rrule(freq=RR.DAILY,until=until)
                elif(ee["repeat_on"] == "Weekly"):
                    for idx, weekday in enumerate(weekdays):
                        if(ee[weekday] == 1):
                            byweekday.append(rrweekdays[idx])
                    rrule = RR.rrule(freq=RR.WEEKLY,until=until,byweekday=byweekday)
                elif(ee["repeat_on"] == "Monthly"):
                    rrule = RR.rrule(freq=RR.MONTHLY,until=until)
                elif(ee["repeat_on"] == "Yearly"):
                    rrule = RR.rrule(freq=RR.YEARLY,until=until)
                
                if(rrule != None):
                    e.add('rrule').value = rrule
                    rstats["mapped"] += 1
                else:
                    rstats["not_mapped"] += 1

                
                #Remove None Children
                none_attributes = []
                for child in e.getChildren():
                    if(child.value == None):
                        none_attributes.append(child.name.lower())
                for attr in none_attributes:
                    e.__delattr__(attr)

                ics = new_calendar.serialize()
                print(ics)
                frappe.db.set_value('Event', ee["name"], 'uid', e.uid.value, update_modified=False)

                #Upload
                if(uploadable):
                    cal.save_event(ics)
                    upstats["10a"] += 1
                else:
                    upstats["not_uploadable"] += 1
            #Case 11a: Status != Open
            else:
                uploadable = False
                upstats["11b"] += 1
        except Exception as ex:
            #traceback.print_exc()
            tb = traceback.format_exc()
            upstats["exceptions"] += 1
            error_stack.append({ "message" : "Could not upload event. Exception: \n" + tb, "event" : json.dumps(ee)})

        #Update UI
        percent_progress = idx / len(erp_events) * 100
        frappe.publish_progress(percent=percent_progress, title="Uploading")


    #Return JSON and Log
    message = {}
    upstats["not_uploadable"] -= upstats["10b"]
    message["upstats"] = upstats
    message["rstats"] = rstats
    message["error_stack"] = error_stack
    

    """
    """

    d = frappe.get_doc("iCalendar", data["icalendar"])
    d.last_sync_log = json.dumps(message)
    d.save()
    d.add_comment('Comment',text="Stats:\n" + str(upstats) + "\nRRule Stats:\n" + str(rstats))

    """
    """

    return json.dumps(message)

@frappe.whitelist()
def sync_calendar(data):
    #Check if called from client side (not necessary)
    if(isinstance(data,str)):
        data = json.loads(data)

    #Connect to CalDav Account
    account = frappe.get_doc("CalDav Account", data["caldavaccount"])
    """
    account = data["caldavaccount"]
    """
    client = caldav.DAVClient(url=account.url, username=account.username, password=account.password)
    principal = client.principal()
    calendars = principal.calendars()

    #Look for the right calendar
    for calendar in calendars:
        if(str(calendar) == data["calendarurl"]):
            cal = calendar
    
    #Go through Events
    events = cal.events()

    #Stats
    stats = {
        "1a" : 0,
        "1b" : 0,
        "1c" : 0,
        "2a" : 0,
        "3a" : 0,
        "3b" : 0,
        "4a" : 0,
        "else" : 0,
        "error" : 0,
        "not_inserted" : 0,
        "exception_block_standard" : 0,
        "exception_block_meta" : 0
    }
    rstats = {
        "norrule" : 0,
        "daily" : 0,
        "weekly" : 0,
        "monthly" : 0,
        "yearly" : 0,
        "finite" : 0,
        "infinite" : 0,
        "total" : len(events),
        "singular_event" :0,
        "error" : 0,
        "exception" :0
    }
    #Error Stack
    error_stack = []

    filters = {
        'icalendar': data["icalendar"]
    }

    erp_events = frappe.db.sql("""
        SELECT
            *
        FROM `tabEvent`
        WHERE icalendar = %(icalendar)s AND custom_pattern is NULL;
    """, filters=filters, as_dict=1)

    erp_cps = frappe.db.sql("""
        SELECT
            *
        FROM `tabCustom Pattern`
        WHERE icalendar = %(icalendar)s);
    """, filters, as_dict=1)

    for erp_event in erp_events:
        
        instructions = [
            {
                "Cmd" : "Copy",
                "From": "A",
                "To"  : "B",
            },
            {
                "Cmd" : "Delete",
                "From": "A"
            },
            {
                "Cmd" : "Conflict"
            }
        ]

        #Retrieve etags
        etaga = erp_event.etag
        vev = event.vobject_instance.vevent
        etagb = etag_event()

        #Get instructions for event
        instr = compile_instructions_for_event(etaga, etagb)


        #Get corresponding objects


        #Do the upload

    

    return None






############################################################ DEBUGGING ##############################

if __name__ == "__main__":


    data = {
        "caldavaccount" : "marius.widmann@tueit.de",
        "calendarurl" : "https://mail.tueit.de/SOGo/dav/marius.widmann%40tueit.de/Calendar/personal/",
        "icalendar" : "Marius",
        "color" : "#ff4d4d"
    }

    message = sync_calendar(data)
    message = json.loads(message)
    print(message["stats"])