import secrets

from django.db import models


class Person(models.Model):
    name = models.CharField(max_length=100)
    phone = models.CharField(max_length=20, help_text="WhatsApp number, e.g. +15551234567")

    def __str__(self):
        return self.name


def generate_token():
    return secrets.token_urlsafe(32)


class Chore(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        REMINDED = "reminded", "Reminded"
        ESCALATED = "escalated", "Escalated"
        DONE = "done", "Done"

    name = models.CharField(max_length=100)
    frequency_days = models.IntegerField(help_text="e.g. 1 = daily, 7 = weekly")
    rotation_order = models.JSONField(help_text="List of Person IDs, in turn order")
    rotation_index = models.IntegerField(default=0, help_text="Index into rotation_order for whose turn it is")
    due_date = models.DateField()
    grace_hours = models.IntegerField(default=24, help_text="Hours after due_date before escalating")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)

    def __str__(self):
        return self.name


class CompletionToken(models.Model):
    token = models.CharField(max_length=64, primary_key=True, default=generate_token, editable=False)
    chore = models.ForeignKey(Chore, on_delete=models.CASCADE, related_name="completion_tokens")
    created_at = models.DateTimeField(auto_now_add=True)
    used = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.chore.name} ({'used' if self.used else 'unused'})"
