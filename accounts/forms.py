from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.hashers import make_password


class RegisterForm(forms.ModelForm):
    """Extended registration form with email field."""

    email = forms.EmailField(required=True)
    password = forms.CharField(widget=forms.PasswordInput)

    class Meta:
        model = User
        fields = ['username', 'email']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            field.widget.attrs['class'] = 'form-input'
            field.widget.attrs['autocomplete'] = 'off'
            
    def save(self, commit=True):
        user = super().save(commit=False)
        user.password = make_password(self.cleaned_data['password'])
        if commit:
            user.save()
        return user


class LoginForm(forms.Form):
    """Simple login form."""

    username = forms.CharField(
        widget=forms.TextInput(attrs={'class': 'form-input', 'autocomplete': 'off'})
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-input'})
    )
