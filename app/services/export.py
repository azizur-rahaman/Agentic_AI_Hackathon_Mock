import csv
import io
from typing import List
from .. import models, timeutils


def generate_bookings_csv(bookings: List[models.Booking]) -> str:
    """
    Generates a CSV string of the bookings with the exact header format:
    id,reference code,room id,user id, start time, end time,status,price cents
    """
    output = io.StringIO()
    # Manual header write to match exact spacing from specifications:
    output.write("id,reference code,room id,user id, start time, end time,status,price cents\r\n")
    
    writer = csv.writer(output, lineterminator="\r\n")
    for b in bookings:
        start_str = timeutils.serialize_dt(b.start_time)
        end_str = timeutils.serialize_dt(b.end_time)
        writer.writerow([
            b.id,
            b.reference_code,
            b.room_id,
            b.user_id,
            start_str,
            end_str,
            b.status,
            b.price_cents
        ])
    return output.getvalue()
