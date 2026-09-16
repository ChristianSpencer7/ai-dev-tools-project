import datetime

from django.test import TestCase

from .models import Chore, CompletionToken, Person
from .rotation import complete_chore, get_current_assignee


def make_chore(people, frequency_days=7, rotation_index=0, status=Chore.Status.PENDING, due_date=None):
    return Chore.objects.create(
        name="Take out trash",
        frequency_days=frequency_days,
        rotation_order=[p.id for p in people],
        rotation_index=rotation_index,
        due_date=due_date or datetime.date.today(),
        status=status,
    )


class PersonModelTests(TestCase):
    def test_creates_person_with_name_and_phone(self):
        person = Person.objects.create(name="Alice", phone="+15551110001")
        person.refresh_from_db()
        self.assertEqual(person.name, "Alice")
        self.assertEqual(person.phone, "+15551110001")

    def test_str_returns_name(self):
        person = Person.objects.create(name="Alice", phone="+15551110001")
        self.assertEqual(str(person), "Alice")


class ChoreModelTests(TestCase):
    def test_defaults_on_creation(self):
        alice = Person.objects.create(name="Alice", phone="+15551110001")
        chore = make_chore([alice])
        self.assertEqual(chore.rotation_index, 0)
        self.assertEqual(chore.status, Chore.Status.PENDING)
        self.assertEqual(chore.grace_hours, 24)

    def test_str_returns_name(self):
        alice = Person.objects.create(name="Alice", phone="+15551110001")
        chore = make_chore([alice])
        self.assertEqual(str(chore), "Take out trash")

    def test_rotation_order_round_trips_as_list(self):
        alice = Person.objects.create(name="Alice", phone="+15551110001")
        bob = Person.objects.create(name="Bob", phone="+15551110002")
        chore = make_chore([alice, bob])
        chore.refresh_from_db()
        self.assertEqual(chore.rotation_order, [alice.id, bob.id])
        self.assertIsInstance(chore.rotation_order, list)


class CompletionTokenModelTests(TestCase):
    def setUp(self):
        self.alice = Person.objects.create(name="Alice", phone="+15551110001")
        self.chore = make_chore([self.alice])

    def test_token_is_auto_generated_and_unique(self):
        token1 = CompletionToken.objects.create(chore=self.chore)
        token2 = CompletionToken.objects.create(chore=self.chore)
        self.assertTrue(token1.token)
        self.assertTrue(token2.token)
        self.assertNotEqual(token1.token, token2.token)

    def test_used_defaults_to_false(self):
        token = CompletionToken.objects.create(chore=self.chore)
        self.assertFalse(token.used)

    def test_created_at_is_set_automatically(self):
        token = CompletionToken.objects.create(chore=self.chore)
        self.assertIsNotNone(token.created_at)

    def test_str_reflects_used_state(self):
        token = CompletionToken.objects.create(chore=self.chore)
        self.assertIn("unused", str(token))
        token.used = True
        token.save()
        self.assertIn("used", str(token))

    def test_deleting_chore_cascades_to_tokens(self):
        token = CompletionToken.objects.create(chore=self.chore)
        self.chore.delete()
        self.assertFalse(CompletionToken.objects.filter(token=token.token).exists())


class GetCurrentAssigneeTests(TestCase):
    def test_returns_person_at_index_zero(self):
        alice = Person.objects.create(name="Alice", phone="+15551110001")
        bob = Person.objects.create(name="Bob", phone="+15551110002")
        chore = make_chore([alice, bob], rotation_index=0)
        self.assertEqual(get_current_assignee(chore), alice)

    def test_returns_person_mid_rotation(self):
        alice = Person.objects.create(name="Alice", phone="+15551110001")
        bob = Person.objects.create(name="Bob", phone="+15551110002")
        chore = make_chore([alice, bob], rotation_index=1)
        self.assertEqual(get_current_assignee(chore), bob)

    def test_single_person_rotation(self):
        alice = Person.objects.create(name="Alice", phone="+15551110001")
        chore = make_chore([alice], rotation_index=0)
        self.assertEqual(get_current_assignee(chore), alice)


class CompleteChoreTests(TestCase):
    def test_advances_rotation_index(self):
        alice = Person.objects.create(name="Alice", phone="+15551110001")
        bob = Person.objects.create(name="Bob", phone="+15551110002")
        chore = make_chore([alice, bob], rotation_index=0)

        complete_chore(chore)

        self.assertEqual(chore.rotation_index, 1)

    def test_wraps_around_at_end_of_rotation(self):
        alice = Person.objects.create(name="Alice", phone="+15551110001")
        bob = Person.objects.create(name="Bob", phone="+15551110002")
        carol = Person.objects.create(name="Carol", phone="+15551110003")
        chore = make_chore([alice, bob, carol], rotation_index=2)

        complete_chore(chore)

        self.assertEqual(chore.rotation_index, 0)

    def test_recomputes_due_date(self):
        alice = Person.objects.create(name="Alice", phone="+15551110001")
        chore = make_chore([alice], frequency_days=7, due_date=datetime.date(2026, 1, 1))

        complete_chore(chore)

        self.assertEqual(chore.due_date, datetime.date.today() + datetime.timedelta(days=7))

    def test_resets_status_to_pending_from_reminded(self):
        alice = Person.objects.create(name="Alice", phone="+15551110001")
        chore = make_chore([alice], status=Chore.Status.REMINDED)

        complete_chore(chore)

        self.assertEqual(chore.status, Chore.Status.PENDING)

    def test_resets_status_to_pending_from_escalated(self):
        alice = Person.objects.create(name="Alice", phone="+15551110001")
        chore = make_chore([alice], status=Chore.Status.ESCALATED)

        complete_chore(chore)

        self.assertEqual(chore.status, Chore.Status.PENDING)

    def test_persists_changes_to_database(self):
        alice = Person.objects.create(name="Alice", phone="+15551110001")
        bob = Person.objects.create(name="Bob", phone="+15551110002")
        chore = make_chore([alice, bob], rotation_index=0)

        complete_chore(chore)

        reloaded = Chore.objects.get(pk=chore.pk)
        self.assertEqual(reloaded.rotation_index, 1)
        self.assertEqual(reloaded.status, Chore.Status.PENDING)

    def test_single_person_rotation_stays_at_index_zero(self):
        alice = Person.objects.create(name="Alice", phone="+15551110001")
        chore = make_chore([alice], rotation_index=0)

        complete_chore(chore)

        self.assertEqual(chore.rotation_index, 0)


class RotationIntegrationTests(TestCase):
    def test_full_cycle_returns_to_original_assignee(self):
        alice = Person.objects.create(name="Alice", phone="+15551110001")
        bob = Person.objects.create(name="Bob", phone="+15551110002")
        chore = make_chore([alice, bob], rotation_index=0)

        self.assertEqual(get_current_assignee(chore), alice)

        complete_chore(chore)
        self.assertEqual(get_current_assignee(chore), bob)

        complete_chore(chore)
        self.assertEqual(get_current_assignee(chore), alice)
