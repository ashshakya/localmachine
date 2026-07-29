from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.forms import EmailField, EmailInput


def normalize_account_email(value):
    return get_user_model().objects.normalize_email(value.strip()).lower()


class EmailRegistrationForm(UserCreationForm):
    email = EmailField(
        label="Email address",
        max_length=254,
        widget=EmailInput(attrs={"autocomplete": "email"}),
    )

    class Meta:
        model = get_user_model()
        fields = ("email",)

    def clean_email(self):
        email = normalize_account_email(self.cleaned_data["email"])
        if get_user_model().objects.filter(
            Q(username__iexact=email) | Q(email__iexact=email)
        ).exists():
            raise ValidationError("An account with this email already exists.")
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]
        user.username = self.cleaned_data["email"]
        if commit:
            user.save()
        return user


class EmailAuthenticationForm(AuthenticationForm):
    error_messages = {
        **AuthenticationForm.error_messages,
        "invalid_login": "Enter a correct email address and password.",
    }
    username = EmailField(
        label="Email address",
        max_length=254,
        widget=EmailInput(attrs={"autofocus": True, "autocomplete": "email"}),
    )

    def clean(self):
        email = self.cleaned_data.get("username")
        if email:
            self.cleaned_data["username"] = normalize_account_email(email)
        return super().clean()
