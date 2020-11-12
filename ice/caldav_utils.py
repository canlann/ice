import datetime
import sys

## We'll try to use the local caldav library, not the system-installed
sys.path.insert(0, '..')

import dateutil
import re

def isMappable(vev, rule):
    #Ausschluss EXDATE, EXRULE, RDATE (https://www.kanzaki.com/docs/ical/)
    if(hasattr(vev,"exdate") or hasattr(vev,"rdate") or hasattr(vev,"exrule")):
        return False

    #Auschluss von Intervalregeln
    if rule._interval is not None:
        if(rule._interval != 1):
            return False

    #Ausschluss von e.g. (2TH oder BYMONTH=-1TU)
    match = re.search(r'\b(?:\d.{2}|BY.{0,5}=-?\d.{2})\b',vev.rrule.value)
    if match:
        return False
    else:
        return True

def noByDay(rrulestr):
    match = re.search(r'\b(?:BY.{0,5}DAY)\b',rrulestr)
    if match:
        return False
    else:
        return True

def isNotFebruaryException(dtstartdate):
    if dtstartdate.day <= 28:
        return True
    else:
        return False

def getUntil(dtstartdate,rrule):
    if(rrule._until):
        return rrule._until
    elif(rrule._count):
        extra_days = datetime.timedelta(days=rrule._count)
        return (dtstartdate + extra_days)
    else:
        return None

def isUntilNaive(rrulestr):
    match = re.search(r'UNTIL=\d*T\d*[A-Z]+|UNTIL=\d*[A-Z]+',rrulestr)
    if match:
        return False
    else:
        return True

#DEPRECATED
def preprocessingVeventInstance(vev):
    #Type conversions
    if(type(vev.dtstart.value) is datetime.date):
        vev.dtstart.value = datetime.datetime(year=vev.dtstart.value.year, month=vev.dtstart.value.month, day=vev.dtstart.value.day)
    if(hasattr(vev,"dtend")):
        if(type(vev.dtend.value) is datetime.date):
            vev.dtend.value = datetime.datetime(year=vev.dtend.value.year, month=vev.dtend.value.month, day=vev.dtend.value.day)

    #Timezone (make naive)
    if vev.dtstart.value.utcoffset() is not None: # if dtstart has tzinfo
        vev.dtstart.value = vev.dtstart.value.replace(tzinfo=dateutil.tz.tzutc())
        if hasattr(vev,"rrule") and isUntilNaive(vev.rrule.value): # if util has not tzinfo
            vev.dtstart.value = vev.dtstart.value.replace(tzinfo=None)

    if(hasattr(vev,"dtend") and vev.dtend.value.utcoffset() is not None):
        vev.dtend.value = vev.dtend.value.replace(tzinfo=dateutil.tz.tzutc())

    return vev

#UNDER CONSTRUCTION
def makeComparable(vev):
    #Set tzinfo
    tz = None

    #Change tzinfo
    for child in vev.getChildren():
        changed = False
        if isinstance(child,list):
            new_child = []
            for item in child:
                if type(item) is datetime.datetime:
                    new_item = datetime.datetime(item.year,item.month,item.day,item.hour,item.minute,item.second,tzinfo=tz)
                    changed = True
                    new_child.append(new_item)
                elif type(item) is datetime.date:
                    new_item = datetime.datetime(item.year,item.month,item.day,tzinfo=tz)
                    changed = True
                    new_child.append(new_item)
            child = new_child
        
    
    #if(hasattr(vev,"exdate")):
    #    new_exdate = []
    #    for dt in vev.exdate.value:
    #        new_exdate.append(dt.replace(tzinfo=None))
    #    vev.exdate.value = new_exdate
    
    
    return vev


#UNDER CONSTRUCTION
def toNaiveFromVobjVevent(vev):

    import vobject
    
    #This makes a vevent timezone naive
    vevstr = vev.serialize()
    vevstr = re.sub(r', tzinfo=[^\)]*\)','',vevstr)
    vevstr = re.sub(r'(?<=\d{8}T\d{6})Z','',vevstr)
    vevstr = re.sub(r'(?<=\d{8}T\d{4})Z','',vevstr)
    vevstr = re.sub(r'(?<=\d{8})Z','',vevstr)

    icalstr = "BEGIN:VCALENDAR\nVERSION:2.0\nPRODID:-//PYVOBJECT//NONSGML Version 1//EN\n" + vevstr + "END:VCALENDAR" #...make it a calendar vobject, check type, extract event

    vev = vobject.readOne(vevstr)
    return vev.vevent