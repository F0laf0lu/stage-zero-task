from django.db import models
from django.contrib.auth import get_user_model
from django.contrib.auth.models import BaseUserManager, AbstractBaseUser, AbstractUser
import uuid6
from django.core.validators import MinValueValidator, MaxValueValidator




class UserManager(BaseUserManager):
    
    def create_user(self, email, password=None, **extra_fields):
        if email is None:
            raise ValueError("Email is required")
        
        email = self.normalize_email(email)
        user = self.model(email=email, **self.extra)
        user.set_password()
        user.save(using=self._db)
        return user
    




class User(AbstractUser):
    
    class UserRole(models.TextChoices):
        ADMIN = "ADMIN"
        ANALYST = "ANALYST"

    id = models.UUIDField(primary_key=True, default=uuid6.uuid7, editable=False)
    github_id = models.CharField(max_length=255)
    email = models.EmailField(unique=True)
    avatar_url = models.TextField()
    role = models.CharField(max_length=255, choices=UserRole.choices)
    created_at = models.DateTimeField(auto_now_add=True)



class Profile(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid6.uuid7, editable=False)
    name = models.CharField(max_length=255, unique=True)
    gender = models.CharField(max_length=10)
    gender_probability = models.FloatField(
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)])
    age = models.PositiveIntegerField()
    age_group = models.CharField(max_length=20)
    country_id = models.CharField(max_length=2)
    country_name = models.CharField(max_length=255, null=True, blank=True)
    country_probability = models.FloatField(
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)])
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["gender"]),
            models.Index(fields=["age_group"]),
            models.Index(fields=["country_id"]),
            models.Index(fields=["age"]),
        ]

    def __str__(self):
        return self.name


