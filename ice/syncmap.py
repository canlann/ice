from ice.jcache import JCache
import functools 
import hashlib
import datetime

#Source: https://unterwaditzer.net/2016/sync-algorithm.html

class SyncMap:
    def __init__(self,identifier):
        """
        The identifier is e.g. the account + calendar name / address book name... must be unique.
        E.g. CalDav-Resource URL...
        """
        self.identifier = identifier
        self.cache = JCache()
        self.status = {}
        self.load(self.identifier)

    def __del__(self):
        self.save()

    def etag(self, uid, created, last_modified):
        """
        Generates an etag for an item. The datetime values should include seconds (not a requirement).
        """
        etag_raw = uid + last_modified.strftime("%F %T") + created.strftime("%F %T")
        etag = hashlib.md5(etag_raw.encode('utf-8')).hexdigest()
        return etag

    def delete_status(self, uid):
        """
        Delete the status etag entries for a certain item. This is the same as update_status(uid, None, None).
        """
        self.update_status(uid)
    
    def update_status(self, uid, etaga = None, etagb = None):
        """
        After a successfull sync of the item this function needs to be called. If both tags are None the status entry will be deleted.
        """
        try:
            if(uid and (etaga or etagb)):
                if(etaga == None):
                    etaga = etagb
                elif(etagb == None):
                    etagb = etaga
                elif(etaga == None and etagb == None):
                    raise Exception("Must supply at least one etag.")

                uid = str(uid)
                new_entry = [etaga,etagb]
                entry = self.status.setdefault(uid,new_entry)
                if functools.reduce(lambda x, y : x and y, map(lambda p, q: p == q,entry,new_entry), True): 
                    # Status did not change (entry === new_entry)
                    pass
                else: 
                    # Status changed
                    self.status[uid] = new_entry
                return
            elif(uid):
                uid = str(uid)
                del self.status[uid]
        except KeyError as e:
            raise Exception("Synchronization Error. There is no cached entry for item with UID " + str(uid))

    def load(self, identifier):
        """
        Restores all classvariables from the persistent storage.
        Is getting called from __init__()
        """
        try:
            self.status = self.cache.fetch(identifier)
        except:
            self.status = {}

    def save(self):
        """
        Saves all classvariables to the persistent storage.
        Is also getting called on obj.__del__()
        """
        self.cache.stash(self.identifier, self.status)
    
    def compile_instruction(self, uid = None, a = None, b = None):
        """
        @Parameters
        uid = Universal Identifier of the item
        a = etag of the local item if exists
        b = etag of the remote item if exists

        @Returns 
        The instructions on what needs to be done with two corresponding events ( = an event with the same uid).
        The instruction returned has three possible Cmd Values:
        - Copy (From 'Source' to 'Target[]')
        - Delete (From 'Source[]')
        - Conflict

        E.g.:
        {
            "Cmd" : "Copy",
            "Source" : "A",
            "Target" : ["B", "status"]
        }
        """

        statustags = self.status.get(uid) 
        if(a and not b and not statustags):
            instruction = {
                "Cmd" : "Copy",
                "Source" : "A",
                "Target" : ["B", "status"]
            }
            return instruction
        elif(not a and b and not statustags):
            instruction = {
                "Cmd" : "Copy",
                "Source" : "B",
                "Target" : ["A", "status"]
            }
            return instruction
        elif(a and not b and statustags):
            instruction = {
                "Cmd" : "Delete",
                "Source" : ["A","status"]
            }
            return instruction
        elif(not a and b and statustags):
            instruction = {
                "Cmd" : "Delete",
                "Source" : ["B","status"]
            }
            return instruction
        elif(a and b and not statustags):
            instruction = {
                "Cmd" : "Conflict"
            }
            return instruction
        elif(not a and not b and statustags):
            instruction = {
                "Cmd" : "Delete",
                "Source" : ["status"]
            }
            return instruction
        elif(a and b and statustags):
            if(statustags[0] != a and statustags[1] == b):
                instruction = {
                    "Cmd" : "Copy",
                    "Source" : "A",
                    "Target" : ["B","status"]
                }
                return instruction
            elif(statustags[0] == a and statustags[1] != b):
                instruction = {
                    "Cmd" : "Copy",
                    "Source" : "B",
                    "Target" : ["A","status"]
                }
                return instruction
            elif(statustags[0] != a and statustags[1] != b):
                instruction = {
                    "Cmd" : "Conflict"
                }
                return instruction
            else:
                raise Exception("Synchronisation Error. Modification of item with UID " + str(uid) + " locally and remote.")
        else:
            raise Exception("Synchronisation Error. Unseen case for item with UID " + str(uid))

    def getInstruction(self, uid, dtscreated, dtslastmodified):
        """
        This routine is a convenient method. Basically it is the same as compile_instruction, but it creates the etags by itself.
        """
        #Get instructions for event
        etaga = self.etag(uid, dtscreated[0], dtslastmodified[0])
        etagb = self.etag(uid, dtscreated[1], dtslastmodified[1])
        instruction = self.compile_instruction(uid,etaga,etagb)
        return instruction
