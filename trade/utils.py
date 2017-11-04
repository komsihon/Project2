import time


def generate_tx_code(mongo_id, rel_id):
    """
    Transaction codes are a shorter values for MongoDB IDs. Given a MongoDB ID,
    that we know is obtained by concatenating hex values of timestamp, process ID
    and an auto-increment, the transaction code will be obtained by:
    1 - Replacing the timestamp by the ks_timestamp. ks_timestamp is the
    timestamp minus 1464739200 (Number of seconds between Jan 1st, 1970 00:00:00
    and June 1st, 2016, 00:00:00)
    2 - Replacing the process ID by the rel_id where rel_id is rather Autoinc ID from
    the relational DB backend
    3 - Replacing the 3 bytes auto-increment by a 1 byte auto-increment. This is
    done by doing modulo 256 on the value represented by the 3 last bytes of the
    original MongoDB ID.

    :param mongo_id:
    :param rel_id:
    :return: Concatenation of 2, 1 and 3
    """
    c = 1464739200  # Number of seconds between Jan 1st, 1970 00:00:00 and June 1st, 2016, 00:00:00
    cts = int(time.time()) - c
    return hex(rel_id)[2:] + hex(cts)[2:] + mongo_id[-6:]
