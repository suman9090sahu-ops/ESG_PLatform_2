"""
Authentication and Password Management Forms for MEIL ESG CONTROL TOWER.
"""

from django import forms
from django.contrib.auth.forms import (
    AuthenticationForm,
    PasswordChangeForm,
    PasswordResetForm,
    SetPasswordForm,
)


class LoginForm(AuthenticationForm):
    """
    Production-grade login form with Bootstrap 5 styling, accessible attributes,
    and enterprise-safe error messages.
    """

    username = forms.CharField(
        label="Username / Enterprise ID",
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Enter username or enterprise ID",
                "autocomplete": "username",
                "autofocus": True,
                "aria-required": "true",
            }
        ),
    )
    password = forms.CharField(
        label="Password",
        widget=forms.PasswordInput(
            attrs={
                "class": "form-control",
                "placeholder": "Enter password",
                "autocomplete": "current-password",
                "aria-required": "true",
            }
        ),
    )
    remember_me = forms.BooleanField(
        required=False,
        initial=False,
        label="Keep me signed in for 8 hours",
        widget=forms.CheckboxInput(
            attrs={
                "class": "form-check-input",
            }
        ),
    )

    error_messages = {
        "invalid_login": (
            "Invalid credentials. Please verify your username and password, or contact your MEIL system administrator."
        ),
        "inactive": (
            "This enterprise account has been deactivated. Please contact your MEIL compliance officer."
        ),
    }

    def clean(self):
        username = self.cleaned_data.get("username")
        password = self.cleaned_data.get("password")

        if username is not None and password:
            from django.contrib.auth import authenticate, get_user_model

            self.user_cache = authenticate(
                self.request, username=username, password=password
            )
            if self.user_cache is None:
                User = get_user_model()
                try:
                    user_obj = User.objects.get(username=username)
                    if user_obj.check_password(password) and not user_obj.is_active:
                        raise forms.ValidationError(
                            self.error_messages["inactive"],
                            code="inactive",
                        )
                except User.DoesNotExist:
                    pass
                raise self.get_invalid_login_error()
            else:
                self.confirm_login_allowed(self.user_cache)

        return self.cleaned_data


class CustomPasswordChangeForm(PasswordChangeForm):
    """
    Bootstrap 5 styled password change form for authenticated users.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            field.widget.attrs.update({"class": "form-control"})


class CustomPasswordResetForm(PasswordResetForm):
    """
    Bootstrap 5 styled password reset request form.
    """

    email = forms.EmailField(
        label="Registered Enterprise Email",
        max_length=254,
        widget=forms.EmailInput(
            attrs={
                "class": "form-control",
                "placeholder": "name@meilgroup.com",
                "autocomplete": "email",
                "aria-required": "true",
            }
        ),
    )


class CustomSetPasswordForm(SetPasswordForm):
    """
    Bootstrap 5 styled new password confirmation form.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            field.widget.attrs.update({"class": "form-control"})
