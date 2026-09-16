import datetime

from .models import Chore, Person


def get_current_assignee(chore: Chore) -> Person:
    person_id = chore.rotation_order[chore.rotation_index]
    return Person.objects.get(id=person_id)


def complete_chore(chore: Chore) -> None:
    chore.rotation_index = (chore.rotation_index + 1) % len(chore.rotation_order)
    chore.due_date = datetime.date.today() + datetime.timedelta(days=chore.frequency_days)
    chore.status = Chore.Status.PENDING
    chore.save()
