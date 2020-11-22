import frappe
import datetime
import sys
import json

## We'll try to use the local caldav library, not the system-installed
sys.path.insert(0, '..')

import caldav
import dateutil
import re
from ice.caldav_utils import *

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
def sync_calendar(data):
    #Check if called from client side (not necessary)
    if(isinstance(data,str)):
        data = json.loads(data)

    #Connect to CalDav Account
    account = frappe.get_doc("CalDav Account", data["caldavaccount"])
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
        "error" : 0,
        "exception" :0
    }
    #Error Stack
    error_stack = []

    processing = 0
    for event in events:
        vev = event.vobject_instance.vevent
        processing += 1
        #print(processing + "/" + str(len(events)))

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
                timedelta = vev.duration.value
                days = ((dtstart + vev.duration.value).date() - dtstart.date()).days

            #Standard Fields
            doc = frappe.new_doc("Event")
            doc.subject = vev.summary.value
            doc.starts_on = dtstart.strftime("%Y-%m-%d %H:%M:%S")
            doc.uid = vev.uid.value
            doc.caldav_calendar = data["caldavcalendar"]
            if(hasattr(vev,"description")):
                doc.description = vev.description.value
            doc.event_type = "Public"
            if(hasattr(vev, "class")):
                #doc.event_type = "Public"
                pass
            
            insertable = False
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
            elif((hasattr(vev,"dtend") and timedelta.days >= 1)):
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
            print(traceback.format_exc())
            vev.prettyPrint()
            insertable = False
            stats["exception_block_standard"] += 1
            error_stack.append({ "message" : "Problem with Standard Fields/Cases", "icalendar" : vev.serialize()})

        try:
            #RRULE CONVERSION
            mapped = False
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
                #Not mappable but finite
                elif(re.search(r'UNTIL|COUNT',vev.rrule.value)):
                    datetimes = list(vev.getrruleset())
                    rstats["finite"] += 1
                #Not mappable and infinite
                else:
                    vev.rrule.value = vev.rrule.value + ";UNTIL=" + (datetime.datetime.now() + datetime.timedelta(days=10)).strftime("%Y%m%d")
                    datetimes = list(vev.getrruleset())
                    #print(str(len(list(vev.getrruleset()))))
                    rstats["infinite"] += 1
            else:
                mapped = True
                rstats["norrule"] += 1
        
        except Exception as ex:
            #print(traceback.format_exc())
            #vev.prettyPrint()
            mapped = False
            rstats["exception"] += 1
            error_stack.append({ "message" : str(ex), "icalendar" : vev.serialize()})

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
            
            #Insert
            if(insertable and mapped):
                if(hasattr(vev,"last_modified")):
                    doc.last_modified = vev.last_modified.value.strftime("%Y-%m-%d %H:%M:%S")
                if(hasattr(vev,"created")):
                    doc.created_on = vev.created.value.strftime("%Y-%m-%d %H:%M:%S")
                doc.insert(
                        ignore_permissions=False, # ignore write permissions during insert
                        ignore_links=True, # ignore Link validation in the document
                        ignore_if_duplicate=True, # dont insert if DuplicateEntryError is thrown
                        ignore_mandatory=False # insert even if mandatory fields are not set
                )
            else:
                stats["not_inserted"] += 1
        
        except Exception as ex:
            stats["exception_block_meta"] += 1
            error_stack.append({ "message" : "Problem with Meta fields or doc insertion", "icalendar" : vev.serialize()})
 
    #Return JSON and Log
    message = {}
    logtext = "--------------------------------CALDAV Calendar SYNC LOG------------------------\n"
    logtext += "Error Stack:\n"
    for error in error_stack:
        logtext += error["message"] + "\n"
        logtext += error["icalendar"] + "\n"
    logtext += "Stats:\n"
    logtext += str(stats) + "\n"
    logtext += "RRule Stats:\n"
    logtext += str(rstats) + "\n"
    logtext += "-----------------------------------------------------END------------------------\n"

    message["stats"] = stats
    message["rstats"] = rstats
    message["error_stack"] = error_stack

    d = frappe.get_doc("iCalendar", data["caldavcalendar"])
    d.last_sync_log = json.dumps(message)
    d.save()
    d.add_comment('Comment',text="Stats:\n" + str(stats) + "\nRRule Stats:\n" + str(rstats))

    return json.dumps(message)
