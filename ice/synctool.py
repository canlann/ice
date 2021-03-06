from ice.syncmap import SyncMap
#from frappe.frappe import frappe
import frappe
import sys
from frappe.utils.dateutils import *
import caldav
from ice.caldav_utils import *
import json
import datetime
import dateutil
import dateutil.rrule as RR
import vobject
import traceback
import pytz
import pickle
from ice.jsonencoder import ComplexEncoder
from ice.jcache import JCache

## We'll try to use the local caldav library, not the system-installed
sys.path.insert(0, '..')

class SyncTool:
    def __init__(self, accounturl, ressourceurl, username, password, icalendar):
        self.syncmap = SyncMap(ressourceurl)
        self.client = caldav.DAVClient(url=accounturl, username=username, password=password)
        self.principal = self.client.principal()
        self.calendars = self.principal.calendars()
        self.synchronized_uids = []
        self.icalendar = frappe.get_doc("iCalendar", icalendar)
        self.log = []

        #Look for the right calendar
        for calendar in self.calendars:
            if(str(calendar) == ressourceurl):
                self.calendar = calendar

        # Load Events/Custom Patterns
        self.docs_event = frappe.db.sql(f"""
            SELECT
                *
            FROM `tabEvent`
            WHERE icalendar = "{icalendar}" AND custom_pattern is NULL;
            """, as_dict=1)
        self.docs_custom_pattern = frappe.db.sql(f"""
            SELECT
                *
            FROM `tabCustom Pattern`
            WHERE icalendar = "{icalendar}";
            """, as_dict=1)

        #Create backups
        timestamp = datetime.datetime.now().strftime("%F %T")
        self.backupRemote(timestamp)
        self.backupLocal(timestamp)

        #Look for the right vtodo...

    def __del__(self):
        del self.syncmap
        self.dump()

    def cleanseFilename(self,filename):
        filename = re.sub(r'[^a-zA-Z0-9\-]','', filename)
        return filename

    def backupLocal(self, timestamp):
        """
        Dump Events and Custom Pattern from SQL to pickle
        """
        # Backup Events
        filename = timestamp + str(self.calendar) + "_events.pickle"
        filename = self.cleanseFilename(filename)
        pickle.dump(self.docs_event, open( filename , "wb"))

        # Backup Custom Pattern
        filename = timestamp + str(self.calendar) + "_custom_pattern.pickle"
        filename = self.cleanseFilename(filename)
        pickle.dump(self.docs_custom_pattern, open( filename , "wb"))

    def backupRemote(self, timestamp):
        """
        Dump Remote with Pickle.
        """
        # Backup Caldav Calendar Object
        filename = timestamp + str(self.calendar) + "_caldavobject.pickle"
        filename = self.cleanseFilename(filename)
        pickle.dump( self.calendar, open( filename , "wb" ) )
        # Reverse is pickle.load( open( "save.pickle", "rb" ) )
        pass

    def saveItemRemote(self, vcalendarics = None, caldavevent = None):
        """
        Whenever saving an Item on the remote side, use this function. If for testing purposes saving should be interuppted, just uncomment the lines of code in this method.
        """
        if(vcalendarics):
            #self.calendar.save_event(vcalendarics)
            pass
        if(caldavevent):
            #caldavevent.save()
            pass
        
        return

    def deleteItemRemote(self, caldavevent = None):
        """
        Whenever deleting an Item on the remote side, use this function. If for testing purposes saving should be interuppted, just uncomment the lines of code in this method.
        """
        if(caldavevent):
            #caldavevent.save()
            pass

        return

    def imputeVev(self, vev):
        """
        By impute is meant to add missing values, that are necessary for processing.
        Paramter: vevent
        Returns: vevent
        """
        # Impute missing values
        if(not hasattr(vev, "created")):
            vev.add("created").value = vev.dtstamp.value
        if(not hasattr(vev,"last_modified")):
            vev.add("last-modified").value = vev.created.value

        # to UTC
        vev = self.toUTC(vev, changeTz=False,removeVobjOriginalTz=True,removeTzInfo=True)

        return vev

    def toUTC(self, vev, changeTz = True, removeVobjOriginalTz = True, removeTzInfo = False):
        """
        If run with default parameters this will change the vevent object. It will remove original timezone information and recalculate datetimes to timezone UTC.
        If run with parameters changeTZ=False, removeVobjOriginalTz=True, removeTzInfo=True this will change the vevent object. It will remove original timezone information, but it will not recalculate the datetime objects.
        If the Users are all in the same timezone, this option will be sufficient.
        If the Users are in different timezones it will be necessary to add timezone information whenever accessing or storing datetime object in ERP. There must be datetime settings in ERP somewhere (This is not implemented yet).
        Sources: https://vinta.ws/code/timezone-in-python-offset-naive-and-offset-aware-datetimes.html
        """
        # Forked from change_tz.py : change_tz(cal, PyICU.ICUtzinfo.default, PyICU.ICUtzinfo.default, utc_only = False)
        nodenames = ["dtstart", "dtend"] #Datetime components to convert
        utc_only = False
        utc_tz = pytz.timezone('UTC')
        new_timezone = pytz.timezone('UTC')#ICUtzinfo.getInstance('UTC')
        for name in nodenames:
            node = None
            if(hasattr(vev,name)):
                node = getattr(vev,name,None)
            else:
                break
            if node:
                dt = node.value
                default = node.value.tzname()
                if (isinstance(dt, datetime.datetime) and
                        (not utc_only or dt.tzinfo == utc_tz)):
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=default)
                    if(changeTz):
                        node.value = dt.astimezone(new_timezone)
                    if(hasattr(node, "params") and removeVobjOriginalTz):
                        if("X-VOBJ-ORIGINAL-TZID" in node.params):
                            node.params.pop("X-VOBJ-ORIGINAL-TZID")
                    if(removeTzInfo):
                        node.value.replace(tzinfo=None)
        return vev

    def unawareComparison(self, dt1, operator, dt2):
        """
        This is a helper method when using the synctool within users being all in the same timezone. In general datetimeobjects should ALWAYS be handled timezone aware.
        See method toUTC for more information. If one day this synctool should be changed to handle timezone aware systems, do a backwards search and replace this method wherever it is being called with a simple boolean comaprison.
        """
        if(not dt1.tzname()):
            dt1localized = pytz.utc.localize(dt1)
        else:
            dt1localized = dt1

        if(not dt2.tzname()):
            dt2localized = pytz.utc.localize(dt2)
        else:
            dt2localized = dt2

        if(operator == "lt"):
            return dt1localized < dt2localized
        elif(operator == "gt"):
            return dtlocallized > dt2localized

    def getStats(self):
        stats = {
                    "downstats" : self.downstats,
                    "upstats" : self.upstats,
                    "modifystats" : self.modifystats,
                    "log" : self.log
        }
        return stats


    def dump(self):
        try:
            stats = self.getStats()
            cache = JCache('caldav_last_sync')
            cache.stash("stats",stats)
        except:
            raise("Could not dump synchronization and error information.")
        
    @staticmethod
    def retrieveDump():
        cache = JCache('caldav_last_sync')
        stats = cache.fetch("stats")
        return stats

    def syncEvents(self):
        """
        Syncs all the Events and Custom Patterns by default.
        Default function call: syncEvents()
        Parameters: None
        """
        self.upstats = self.upstats_for_events()
        self.modifystats = self.upstats_for_events()
        self.downstats = self.downstats_for_events()
        self.synchronized_uids = []
        idx = 1


        for doc in self.docs_event:
            event = self.searchEventByUid(doc.uid)
            (synced, uid) = self.syncEvent(event, doc)
            self.synchronized_uids.append(uid)
            print("Sync Event " + str(idx) + "/" + str(len(self.docs_event)))
            idx += 1

        idx = 1
        for doc in self.docs_custom_pattern:
            event = self.searchEventByUid(doc.uid)
            (synced, uid) = self.syncCustomPattern(event, doc)
            self.synchronized_uids.append(uid)
            print("Sync Custom Pattern" + str(idx) + "/" + str(len(self.docs_custom_pattern)))
            idx += 1

        synced_caldav_events = 0
        events = self.calendar.events()
        idx = 1
        for event in events:
            uid = event.vobject_instance.vevent.uid.value
            if uid not in self.synchronized_uids:
                synced = self.syncEvent(event)
                self.synchronized_uids.append(uid)
                synced_caldav_events += 1
                print("Sync CaldavEvent " + str(idx) + "/" + str(len(events)))
                idx += 1
            
            if(idx > 1):
                break

        #Everything done?
        total_to_sync_items = len(self.docs_event) + len(self.docs_custom_pattern) + synced_caldav_events
        if(total_to_sync_items == len(self.synchronized_uids)):
            return
        else:
            raise Exception("Did process to few or two many events.")

    def syncEvent(self, event = None, doc_event = None):
        """
        This synchronizes two events.
        Parameters:
        vev_remote: The vobject event instance of the caldav server. Can be None.
        doc_event: The dict of the ERPNext Event doctype. Can be None.
        One of the parameters has to be != None
        """
        vev_remote = None
        vev_by_doc = None
        vev_updated = None
        vcal_with_new_event = None

        #Get vev_remote
        if(event):
            vev_remote = self.imputeVev(event.vobject_instance.vevent)


        #Generate vev_by_doc if possible
        if(doc_event): #Performance optimization: if(doc_event and not event) => this threw an error in line 317 NoneType for vev_by_doc, status was not correct
            vcal_with_new_event = self.createEvent(doc_event)
            for vevent in vcal_with_new_event.getChildren():
                #Since the vcal_with_new_event has only one vevent in it this loop always has one iteration.
                vev_by_doc = vevent
                print("Log: vev_by_doc after creation")
                vev_by_doc.prettyPrint()

        #Generate a vev_updated version for upload usage
        #If only either a remote or a local version exist take the one that exists
        if(vev_remote and not doc_event):
                vev_updated = vev_remote

        if(vev_remote and doc_event):
            local_is_newer = self.unawareComparison(vev_remote.last_modified.value, "lt", doc_event["last_modified"])
            if(local_is_newer):
                #If the event does exist and local (ERP Event) is newer, overwrite.
                vev_updated = self.modifyEvent(vev_remote, doc_event)
            else:
                #Else: The remote event is newer, so just leave vev as is.
                vev_updated = vev_remote

        #Get synchronization instructions
        is_deleted_local = self.is_deleted_locally(vev_remote, doc_event)
        if(not doc_event and vev_remote):
            etaga = None
            etagb = self.syncmap.etag(vev_remote.uid.value, vev_remote.created.value, vev_remote.last_modified.value)
            uid = vev_remote.uid.value
        elif( doc_event and not vev_remote):
            if(not is_deleted_local):
                etaga = self.syncmap.etag(vev_by_doc.uid.value, vev_by_doc.created.value, vev_by_doc.last_modified.value)
                etagb = None
                uid = vev_by_doc.uid.value
            else:
                return
        elif( doc_event  and vev_remote):
            if(not is_deleted_local):
                print("Log: vev_by_doc before accessing uid")
                vev_by_doc.prettyPrint()
                etaga = self.syncmap.etag(vev_by_doc.uid.value, vev_by_doc.created.value, vev_by_doc.last_modified.value)
                etagb = self.syncmap.etag(vev_remote.uid.value, vev_remote.created.value, vev_remote.last_modified.value)
                uid = vev_by_doc.uid.value or vev_remote.uid.value
            else:
                etaga = None
                etagb = self.syncmap.etag(vev_remote.uid.value, vev_remote.created.value, vev_remote.last_modified.value)
                uid = vev_by_doc.uid.value or vev_remote.uid.value
        else:
            raise Exception("SyncError for event: " + str(doc_event))

        #Get instructions
        instruction = self.syncmap.compile_instruction(uid, etaga, etagb)
        print(instruction)
        #Execute instruction
        if(instruction["Cmd"] == "Copy"):
            for target in instruction["Target"]:
                if(target == "A"):
                    try:
                        # Copy from remote to local
                        is_copied = False
                        if(doc_event):
                            is_copied = self.parseEvent(vev_updated, doc_event["name"])
                        else:
                            is_copied = self.parseEvent(vev_updated)
                        if(is_copied):
                            instruction["Target"].pop("A")
                            instruction["Done"] += 1
                    except:
                        pass

                if(target == "B"):
                    # Copy from local to remote
                    try:
                        if(vev_updated):
                            self.saveItemRemote(caldavevent = event)
                            instruction["Target"].pop("B")
                            instruction["Done"] += 1
                            pass
                        elif(event.vobject_instance.vevent.uid.value == vev_updated.uid.value):
                            self.saveItemRemote(vcalendarics = vcal_with_new_event.serialize())
                            instruction["Target"].pop("B")
                            instruction["Done"] += 1
                        else:
                            raise Exception("UIDs differ where they shouldn't.")
                    except:
                        pass

                if(target == "status" and len(instruction["Target"]) == 1 ):
                    try:
                        self.updateAfterCopyCmd(vev_updated)
                        instruction["Target"].pop("status")
                        instruction["Done"] += 1
                    except:
                        pass
        elif(instruction["Cmd"] == "Delete"):
            for source in instruction["Source"]:
                if(source == "A"):
                    # Delete from local
                    try:
                        self.deleteEventLocally(doc_event["name"])
                        instruction["Source"].pop("A")
                        instruction["Done"] += 1
                    except:
                        pass

                if(source == "B"):
                    # Delete from remote
                    try:
                        self.deleteItemRemote(caldavevent = event)
                        instruction["Source"].pop("B")
                        instruction["Done"] += 1
                    except:
                        pass

                if(source == "status" and len(instruction["Target"]) == 1 ):
                    # Delete from status
                    try:
                        self.syncmap.delete_status(vev_updated.uid.value)
                        instruction["Source"].pop("status")
                        instruction["Done"] += 1
                    except:
                        pass
        elif(instruction["Cmd"] == "Conflict"):
            # Conflict logging or resultion
            try:
                #instruction["Done"] += 1
                pass
            except:
                pass
        else:
            raise Exception("Synchronisation Error. Unknown instruction for syncing event with UID " + str(uid))

        print(instruction)
        #All done?
        if(instruction["Tasks"] == instruction["Done"]):
            return (True, uid)
        else:
            return (False, uid)
    
    def syncCustomPattern(self, event = None, doc_custom_pattern = None):
        vev_remote = None
        #Get vev_remote
        if(event):
            vev_remote = self.imputeVev(event.vobject_instance.vevent)

        #Get synchronization instructions
        is_deleted_local = self.is_deleted_locally(vev_remote, doc_custom_pattern)
        if(not doc_custom_pattern and vev_remote):
            etaga = None
            etagb = self.syncmap.etag(vev_remote.uid.value, vev_remote.created.value, vev_remote.last_modified.value)
            uid = vev_remote.uid.value
        elif(doc_custom_pattern and not vev_remote):
            if(not is_deleted_local):
                etaga = self.syncmap.etag(doc_custom_pattern["uid"], doc_custom_pattern["created"], doc_custom_pattern["last_modified"])
                etagb = None
                uid = doc_custom_pattern["uid"]
            else:
                return
        elif(doc_custom_pattern  and vev_remote):
            if(not is_deleted_local):
                etaga = self.syncmap.etag(doc_custom_pattern["uid"], doc_custom_pattern["created"], doc_custom_pattern["last_modified"])
                etagb = self.syncmap.etag(vev_remote.uid.value, vev_remote.created.value, vev_remote.last_modified.value)
                uid = doc_custom_pattern["uid"] or vev_remote.uid.value
            else:
                etaga = None
                etagb = self.syncmap.etag(vev_remote.uid.value, vev_remote.created.value, vev_remote.last_modified.value)
                uid = doc_custom_pattern["uid"]or vev_remote.uid.value
        else:
            raise Exception("SyncError for Custom Pattern: " + str(doc_custom_pattern))
        
       #Get instructions
        instruction = self.syncmap.compile_instruction(uid, etaga, etagb)
        
        #Execute instruction
        if(instruction["Cmd"] == "Copy"):
            for target in instruction["Target"]:
                if(target == "A"):
                    try:
                        # Copy from remote to local
                        is_copied = False
                        if(doc_custom_pattern):
                            is_copied = self.parseEvent(vev_remote, doc_custom_pattern["name"])
                        else:
                            is_copied = self.parseEvent(vev_remote)
                        if(is_copied):
                            instruction["Target"].pop("A")
                            instruction["Done"] += 1
                    except:
                        pass

                if(target == "B"):
                    # Copy from local to remote
                    raise Exception("Copying a changed Custom Pattern to the Caldav Server is impossible.")

                if(target == "status" and len(instruction["Target"]) == 1 ):
                    try:
                        self.updateAfterCopyCmd(vev_remote)
                        instruction["Target"].pop("status")
                        instruction["Done"] += 1
                    except:
                        pass
        elif(instruction["Cmd"] == "Delete"):
            for source in instruction["Source"]:
                if(source == "A"):
                    # Delete from local
                    try:
                        self.deleteCustomPatternLocally(doc_custom_pattern["name"])
                        instruction["Source"].pop("A")
                        instruction["Done"] += 1
                    except:
                        pass

                if(source == "B"):
                    # Delete from remote
                    try:
                        self.deleteItemRemote(caldavevent = event)
                        instruction["Source"].pop("B")
                        instruction["Done"] += 1
                    except:
                        pass

                if(source == "status" and len(instruction["Target"]) == 1 ):
                    # Delete from status
                    try:
                        self.syncmap.delete_status(vev_remote.uid.value)
                        instruction["Source"].pop("status")
                        instruction["Done"] += 1
                    except:
                        pass
        elif(instruction["Cmd"] == "Conflict"):
            # Conflict logging or resultion
            try:
                #instruction["Done"] += 1
                pass
            except:
                pass
        else:
            raise Exception("Synchronisation Error. Unknown instruction for syncing event with UID " + str(uid))


        #All done?
        if(instruction["Tasks"] == instruction["Done"]):
            return (True, uid)
        else:
            return (False, uid)
    
    def logProblem(self, problem, objecttype, identifier):
        self.log.append([problem, objecttype, identifier])

    def createEvent(self, ee):
        """
        Creates an offline vobject and inserts missing values into the ERPNext Event. This does not save the event to local or remote.
        Parameter: ee is a singular erp event as dict from an frappe sql query.
        Returns:  vobject vcalender object with a singular vevent component or None if not possible to create one.
        """
        weekdays = ["monday","tuesday","wednesday","thursday","friday","saturday","sunday"]
        rrweekdays = [RR.MO,RR.TU,RR.WE,RR.TH,RR.FR,RR.SA,RR.SU]
        upstats = self.upstats
        rstats = self.upstats["rstats"]
        error_stack = self.upstats["error_stack"]
        uid = None
        uploadable = True
        
        try:
            #Case 10a: Status Open, everything nominal
            if(ee["status"] == "Open"):
                new_calendar = vobject.newFromBehavior('vcalendar')
                e  = new_calendar.add('vevent')
                new_calendar.add("prodid")
                new_calendar.prodid.value = '-//iCalendar Extension (ice) module//Marius Widmann//'
                e.add('summary').value = ee["subject"]
                dtstart = ee["starts_on"]
                e.add('dtstart').value = dtstart
                e.add('description').value = ee["description"]
                if(ee["event_type"] in ["Public","Private","Confidential"]):
                    e.add('class').value = ee["event_type"]
                #Case 10b: Status Open, but Event Type is Cancelled
                elif(ee["event_type"] == "Cancelled"):
                    uploadable = False
                    self.logProblem("Event Type Cancelled in Method createEvent()", ee["doctype"], ee["name"])
                    upstats["10b"] += 1
                #Case 10c: Status Open, but Event Type not in [Public, Private, Confidential,Cancelled]
                else:
                    uploadable = False
                    self.logProblem("Event Type not in Public, Private, Confidential or Cancelled in Method createEvent()", ee["doctype"], ee["name"])
                    upstats["10c"] += 1
                    raise Exception('Exception:', 'Event with Name ' + ee["name"] + ' has the invalid Event Type ' + ee["event_type"])
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

                if(ee["uid"] != None):
                    e.add('uid').value = ee["uid"]


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
                if(ee["uid"] == None):
                    frappe.db.set_value('Event', ee["name"], 'uid', e.uid.value, update_modified=False)
                    ee["uid"] = e.uid.value

                #Upload
                if(uploadable):
                    upstats["10a"] += 1
                    return new_calendar
                else:
                    upstats["not_uploadable"] += 1
            #Case 11a: Status != Open
            else:
                upstats["11b"] += 1
        except Exception:
            #traceback.print_exc()
            tb = traceback.format_exc()
            upstats["exceptions"] += 1
            error_stack.append({ "message" : "Could not upload event. Exception: \n" + tb, "event" : json.dumps(ee, cls=ComplexEncoder)})
            
        self.upstats["rstats"] = rstats
        self.upstats["error_stack"] = error_stack
        return None

    def parseEvent(self, vev, doc_name = None, custom_pattern_name = None):
        """
        This parses a vobject vevent and inserts it into ERPNext.
        Parameter: 
        vev is a vevent vobject instance
        doc_name is the name of a document of doctype Event. If None the method creates a new Event in ERP.
        custom_pattern_name is the name of a document of doctype Custom Pattern. If None the method creates a new Event or Custom Pattern in ERP.

        Returns True if insertion was successfull.
        """
        downstats = self.downstats
        rstats = self.downstats["rstats"]
        error_stack = self.downstats["error_stack"]
        days = None
        timedelta = None
        doc = None

        #By default an event is not insertable in ERP
        insertable = False
        inserted = False

        #Create or update flag
        is_a_new_document = False
        if(not doc_name and not custom_pattern_name):
            is_a_new_document = True

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
            if(doc_name == None):
                doc = frappe.new_doc("Event")
            else:
                doc = frappe.get_doc("Event", doc_name)
            """
            doc = DotMap()
            """

            doc.subject = vev.summary.value
            doc.starts_on = dtstart.strftime("%Y-%m-%d %H:%M:%S")
            if(hasattr(vev,"description")):
                doc.description = vev.description.value
            doc.event_type = vev.__getattr__("class").value.title()
            
            #Case 1a: has dtend, within a day
            if((hasattr(vev,"dtend") and days == 0)):
                doc.ends_on = dtend.strftime("%Y-%m-%d %H:%M:%S")
                insertable = True
                downstats["1a"] += 1
            #Case 1b: has duration, within a day
            elif(hasattr(vev,"duration") and days == 0 ):
                doc.ends_on = (dtstart + vev.duration.value).strftime("%Y-%m-%d %H:%M:%S")
                insertable = True
                downstats["1b"] += 1
            #Case 1c: Allday, one day
            elif( timedelta.days == 1 and timedelta.seconds == 0 and dtstart.hour == 0 and dtstart.minute == 0):
                doc.ends_on = ""
                doc.all_day = 1
                insertable = True
                downstats["1c"] += 1
            #Case 2a: Allday, more than one day
            elif(timedelta.days >= 1 and timedelta.seconds == 0):
                doc.ends_on = (dtstart + timedelta).strftime("%Y-%m-%d %H:%M:%S")
                doc.all_day = 1
                insertable = True
                downstats["2a"] += 1
            #Case 3a: has dtend, not within a day
            elif((hasattr(vev,"dtend") and days >= 1)):
                doc.ends_on = (dtstart + timedelta).strftime("%Y-%m-%d %H:%M:%S")
                insertable = True
                downstats["3a"] += 1
            #Case 3b: has duration, not within a day
            elif((hasattr(vev,"duration") and days > 0)):
                doc.ends_on = (dtstart + timedelta).strftime("%Y-%m-%d %H:%M:%S")
                insertable = True
                downstats["3b"] += 1
            #Case else: ( ATM: No dtend, No Duration,...)
            else:
                downstats["else"] += 1
            
        except Exception:
            #traceback.print_exc()
            tb = traceback.format_exc()
            insertable = False
            downstats["exception_block_standard"] += 1
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
        
        except Exception:
            #traceback.print_exc()
            tb = traceback.format_exc()
            mapped = False
            rstats["exception"] += 1
            error_stack.append({ "message" : "RRule mapping error. Exception: \n" + tb, "icalendar" : vev.serialize()})

        try:    
            #Specials: Metafields
            if(hasattr(vev,"transp")):
                if(vev.transp.value == "TRANSPARENT"):
                    doc.color = color_variant(self.icalendar.color)
                elif(vev.transp.value == "OPAQUE"):
                    doc.color = self.icalendar.color
            else:
                doc.color = self.icalendar.color

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
            doc.icalendar = self.icalendar.name
        
            #Insert
            if(insertable and mapped):
                """
                """
                if(is_a_new_document):
                    doc.insert(
                            ignore_permissions=False, # ignore write permissions during insert
                            ignore_links=True, # ignore Link validation in the document
                            ignore_if_duplicate=True, # dont insert if DuplicateEntryError is thrown
                            ignore_mandatory=False # insert even if mandatory fields are not set
                    )
                else:
                    doc.save()
                inserted = True
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
                    vev.rrule.value = vev.rrule.value + ";UNTIL=" + (datetime.datetime.now() + datetime.timedelta(days=90)).strftime("%Y%m%d")
                    datetimes = list(vev.getrruleset())
                    rstats["infinite"] += 1

                #Does not need a Custom Pattern
                if(len(datetimes) == 1):
                    """
                    """
                    if(is_a_new_document): 
                        doc.insert() #TODO Remeber this is a strange case too, cause it has a rrule but only one event
                    else:
                        doc.save()
                    
                    rstats["singular_event"] += 1
                    inserted = True
                #Create Custom Pattern and Linked Events
                else:
                    """
                    cp = DotMap()
                    """
                    if(is_a_new_document):
                        cp = frappe.new_doc("Custom Pattern")
                    else:
                        if(custom_pattern_name == None):
                            cp = frappe.get_doc("Custom Pattern", doc.custom_pattern)
                        else:
                            cp = frappe.get_doc("Custom Pattern", custom_pattern_name)
                    cp.title = vev.summary.value
                    cp.icalendar = self.icalendar.name
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

                    
                    """
                    """
                    if(is_a_new_document):
                        cp.insert()
                    else:
                        cp.save()

                    for dt_starts_on in datetimes:
                        if(cp.events):
                            if(dt_starts_on > cp.events[len(cp.events) - 1].starts_on):
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
                                        event.color = color_variant(self.icalendar.color)
                                    elif(vev.transp.value == "OPAQUE"):
                                        event.color = self.icalendar.color
                                else:
                                    event.color = self.icalendar.color

                                if(hasattr(vev,"description")):
                                    event.description = vev.description.value
                                else:
                                    event.description = None

                                event.repeat_this_event = 1
                                
                                """
                                """
                                event.custom_pattern = cp.name
                                event.insert()
                                cp.append('events', {
                                        'event' : event.name
                                })
                    cp.newest_event_on = datetimes[len(datetimes)-1].strftime("%Y-%m-%d %H:%M:%S")
                    cp.save()
                    inserted = True
                    """
                    """
            #Has no rrule, not mappable and strange for unknown reason
            else:
                downstats["not_inserted"] += 1
        except Exception:
            #traceback.print_exc()
            tb = traceback.format_exc()
            downstats["exception_block_meta"] += 1
            error_stack.append({ "message" : "Problem with Meta fields or doc insertion. Exception: \n" + tb, "icalendar" : vev.serialize()})

        self.downstats["rstats"] = rstats
        self.downstats["error_stack"] = error_stack
        return inserted

    def updateEvent(self, vev, ee):
        """
        Overwrites the components of a vevent (vev), except the UID, with the values of the ERP Event (dict(ee)).
        Returns the new vevent or None if unsuccessfull or errors occurred. 
        """
        weekdays = ["monday","tuesday","wednesday","thursday","friday","saturday","sunday"]
        rrweekdays = [RR.MO,RR.TU,RR.WE,RR.TH,RR.FR,RR.SA,RR.SU]
        modifystats = self.modifystats
        rstats = self.modifystats["rstats"]
        error_stack = self.modifystats["error_stack"]
        uid = None
        vev_original_ics = vev.serialize()

        uploadable = True
        try:
            #Case 10a: Status Open, everything nominal
            if(ee["status"] == "Open"):
                vev = self.addOrChange(vev, "summary", ee["subject"])
                dtstart = ee["starts_on"]
                vev = self.addOrChange(vev, "dtstart", dtstart)
                vev = self.addOrChange(vev, "description", ee["description"])
                if(ee["event_type"] in ["Public","Private","Confidential"]):
                    vev = self.addOrChange(vev, "class", ee["event_type"])
                #Case 10b: Status Open, but Event Type is Cancelled
                elif(ee["event_type"] == "Cancelled"):
                    uploadable = False
                    self.logProblem("Event Type Cancelled in Method createEvent()", ee["doctype"], ee["name"])
                    modifystats["10b"] += 1
                #Case 10c: Status Open, but Event Type not in [Public, Private, Confidential,Cancelled]
                else:
                    uploadable = False
                    self.logProblem("Event Type not in Public, Private, Confidential or Cancelled in Method createEvent()", ee["doctype"], ee["name"])
                    modifystats["10c"] += 1
                    raise Exception('Exception:', 'Event with Name ' + ee["name"] + ' has the invalid Event Type ' + ee["event_type"])
                dtend = ee["ends_on"]
                if(dtend == None):
                        dtend = dtstart + datetime.timedelta(minutes=15)
                        frappe.db.set_value('Event', ee["name"], 'ends_on', dtend, update_modified=False)
                if(ee["all_day"] == 0):
                    vev = self.addOrChange(vev, "dtend", dtend)
                else:
                    vev = self.addOrChange(vev, "dtstart", dtstart.date())
                    dtend = (dtend.date() + datetime.timedelta(days=1))
                    vev = self.addOrChange(vev, "dtend", dtend)

                if(ee["last_modified"] == None):
                    frappe.db.set_value('Event', ee["name"], 'last_modified', ee["modified"].replace(microsecond=0), update_modified=False)
                    vev = self.addOrChange(vev, "last-modified", ee["modified"].replace(microsecond=0))
                else:
                    vev = self.addOrChange(vev, "last-modified", ee["last_modified"])

                if(ee["created_on"] == None):
                    frappe.db.set_value('Event', ee["name"], 'created_on', ee["creation"].replace(microsecond=0), update_modified=False)
                    vev = self.addOrChange(vev, "created", ee["creation"].replace(microsecond=0))
                else:
                    vev = self.addOrChange(vev, "created", ee["created_on"])

                #if(ee["uid"] != None):
                #    vev = self.addOrChange(vev, "uid", ee["uid"])


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
                    vev = self.addOrChange(vev, "rrule", rrule)
                    rstats["mapped"] += 1
                else:
                    rstats["not_mapped"] += 1


                
                #Remove None Children
                none_attributes = []
                for child in vev.getChildren():
                    if(child.value == None):
                        none_attributes.append(child.name.lower())
                for attr in none_attributes:
                    vev.__delattr__(attr)

                if(ee["uid"] == None):
                    frappe.db.set_value('Event', ee["name"], 'uid', vev.uid.value, update_modified=False)
                    #vev = self.addOrChange(vev, "uid", ee["uid"])

                #Upload
                if(uploadable):
                    modifystats["10a"] += 1
                    return vev
                else:
                    modifystats["not_uploadable"] += 1
            #Case 11a: Status != Open
            else:
                modifystats["11b"] += 1
        except Exception:
            #traceback.print_exc()
            tb = traceback.format_exc()
            modifystats["exceptions"] += 1
            error_stack.append({ "message" : "Could not merge event. Exception: \n" + tb, "event" : json.dumps(ee,cls=ComplexEncoder), "vev_ics" : vev_original_ics})
            
        self.modifystats["rstats"] = rstats
        self.modifystats["error_stack"] = error_stack
        return None
        
    def is_deleted_locally(self, vev = None, doc = None):
        """
        This method checks if a Event or Custom Pattern has been deleted locally and can be called e.g.:
        is_deleted_local(vev or doc)
        is_deleted_local(vev)
        is_deleted_local(doc)
        The parameter vev_or_doc needs to be of either a vobject vevent or a doctype Custom Pattern/Event as dict().
        """
        #Check if doc is deleted locally
        is_deleted_local = None
        vev_is_deleted = False
        doc_is_deleted = False
        if(vev): #checking for dtstart is random. right way would be to check for type()
            vev_is_deleted = self.is_vev_deleted_local(vev)
            is_deleted_local = vev_is_deleted
        if(doc):
            doc_is_deleted = self.is_doc_deleted_local(doc)
            is_deleted_local = doc_is_deleted

        if((vev and doc) and (vev_is_deleted != doc_is_deleted)):
            raise Exception("The ERP Event or Custom Pattern with the UID " + str(vev.uid.value) + " is not or is deleted locally?")


        return is_deleted_local

    def is_doc_deleted_local(self, doc):
        """
        Since there are different stati between ICS and ERPNext Events this method checks if a ERP Event or Custom Pattern has been deleted.
        Parameter: doc of doctype Event or Custom Pattern as dict()
        """
        if(doc["status"] not in ["Open"]):
            return True
        elif(hasattr(doc, "event_type")):
            if(doc["event_type"] not in ["Public","Private","Confidential"]):
                return True
        
        return False

    def is_vev_deleted_local(self, vev):
        uid = vev.uid.value
        icalendar_name = self.icalendar.name
        if(hasattr(vev, "uid")):
            docs_event = frappe.db.sql(f"""
                SELECT
                    *
                FROM `tabEvent`
                WHERE icalendar = "{icalendar_name}" AND custom_pattern is NULL AND uid = "{uid}";
                """, as_dict=1)
            docs_custom_pattern = frappe.db.sql(f"""
                SELECT
                    *
                FROM `tabCustom Pattern`
                WHERE icalendar = "{icalendar_name}"  AND uid = "{uid}";
                """, as_dict=1)
            if(len(docs_event) == 1 ^ len(docs_custom_pattern) == 1 ):
                return False
            elif(len(docs_event) == 0 and len(docs_event) == 0):
                return True
            else:
                names = []
                for event in docs_event:
                    names.append(event["name"])
                for cp in docs_custom_pattern:
                    names.append(cp["name"])
                raise Exception("Duplicates", "Name of duplicates ERP Event or Custom Pattern are: " + str(names) + " ICS-String: " + str(vev) )
        else:
            raise Exception("UID does not exist.", "The vevent " + str(vev) + " has no UID. Can not confirm if it exists in ERP.")
    
    def deleteEventLocally(doc_name):
        frappe.db.set_value('Event', doc_name, 'status', 'Closed')

    def deleteCustomPatternLocally(doc_name):
        frappe.db.set_value('Custom Pattern', doc_name, 'status', 'Closed')

    def updateAfterCopyCmd(self, vev):
        etag =  self.syncmap.etag(vev.uid.value, vev.created.value, vev.last_modified.value)
        self.syncmap.update(vev.uid.value,etag) 

    def addOrChange(self, vev, name, value):
        """
        If the vevent has the component with "name" then it will be exchanged with the given value. If not it will be added.
        Careful it does not check for duplicate components lilke EXDATE...
        """
        if(hasattr(vev, name)):
            vev.__delattr__(name)
        vev.add(name).value = value
        return vev

    def downstats_for_events(self):
        """
        This initialises a dict for keeping statistics about the successfully downloaded events.
        """
        events = self.calendar.events()
        downstats = {
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
            "exception_block_meta" : 0,
            "rstats" : {
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
            },
            "error_stack" : []
        }

        return downstats

    def upstats_for_events(self):
        """
        This initialises a dict for keeping statistics about the successfully uploaded events.
        """
        upstats = {
            "10a" : 0,
            "10b" : 0,
            "10c" : 0,
            "11b" : 0,
            "not_uploadable" :0,
            "cancelled_or_closed_of_no_uploadable" :0,
            "exceptions" : 0,
            "rstats" : {
                "mapped" : 0,
                "not_mapped" :0,
            },
            "error_stack" : []
        }
        return upstats

    def searchEventByUid(self, uid):
        """
        Returns one event in a caldav events list with the given uid.
        If not found it will return None.
        """
        for idx, event in enumerate(self.calendar.events()):
            vev = event.vobject_instance.vevent
            if(vev.uid.value == uid):
                return event
        return None

    def isEqualEventsEasy(self, vev1, vev2):
        return vev1 == vev2

    def isEqualEvents(self, vev1, vev2):
        """
        Untestet method.
        This returns a True/False value depening on wether the two events are exactly the same or not.
        """
        c1 = list(vev1.getSortedChildren())
        c2 = list(vev2.getSortedChildren())
        if(len(c1) == len(c2)):
            boollist = self.compareComponents(c1,c2)
            isEqual = self.reduceList(boollist)
            return isEqual
        else:
            return False

# Following methods are untested, under construction or deprecated

    def compareComponents(c1, c2):
        """
        Untestet method.
        This returns a list with True/False values. If the lists are of differing length the return list will be of the length of the shorter list.
        Hence this can not be used to compare two vevents unless the length is checked beforehand.
        Source: https://www.geeksforgeeks.org/python-map-function/
        """
        result = map(lambda x, y: x == y, c1, c2) 
        return list(result)

    def reduceList(result):
        """
        Untestet method.
        This will reduce the comparison of the components lists in compareComponents to a singular value.
        It will find out if the both lists are equal or not.
        Source: https://www.geeksforgeeks.org/reduce-in-python/
        and
        Source: https://www.journaldev.com/37089/how-to-compare-two-lists-in-python
        """
        # importing functools for reduce() 
        import functools 
        are_equal = functools.reduce(lambda a,b : a and b, result)
        return are_equal

    def mergeEvent(self, vev_a, vev_b):
        """
        Not implemented. Thought: Is it possible to merge two ics-strings with prioritizing one over the other and then parsing it back into a vevent?
        For merging two events. This is not perfect, but should do it for now as long as there are no duplicate entries in the ics-string (e.g. EXDATE,...)
        """
        if(vev_a.last_modified.value < vev_b.last_modified.value):
            #Merge b into a
            pass   