import datetime
import json


class ComplexEncoder(json.JSONEncoder):
    """
    Usage:
    my_dict = {'date': datetime.datetime.now()}

    json.dumps(my_dict,cls=ComplexEncoder)
    """
    def default(self, z):
        if isinstance(z, datetime.datetime):
            return (z.strftime("%F %T"))
        elif isinstance(z, datetime.date):
            return (z.strftime("%F %T"))
        else:
            return super().default(z)



