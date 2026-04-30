import uuid6
from django.contrib.auth import get_user_model
from django.db import models

User = get_user_model()


class Token(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid6.uuid7, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True)
    type = models.CharField()
    token = models.TextField()
    is_revoked = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Token - {self.user}"
