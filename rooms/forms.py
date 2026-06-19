from django import forms
from django.contrib.auth.hashers import make_password
from .models import Room


class CreateRoomForm(forms.ModelForm):
    """Form for creating a new chat room."""

    password = forms.CharField(
        required=False,
        widget=forms.PasswordInput(attrs={
            'class': 'form-input',
            'placeholder': 'Leave blank for no password',
        }),
    )

    class Meta:
        model = Room
        fields = ['name', 'description', 'capacity', 'password']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'Room Name',
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-input',
                'placeholder': 'Room Description (optional)',
                'rows': 3,
            }),
            'capacity': forms.NumberInput(attrs={
                'class': 'form-input',
                'min': 2,
                'max': 100,
            }),
        }

    def save(self, commit=True):
        room = super().save(commit=False)
        password = self.cleaned_data.get('password')
        if password:
            room.password = make_password(password)
        if commit:
            room.save()
        return room


class JoinRoomForm(forms.Form):
    """Form for joining a room by code."""

    room_code = forms.CharField(
        max_length=6,
        widget=forms.TextInput(attrs={
            'class': 'form-input',
            'placeholder': 'e.g. ABC123',
            'style': 'text-transform: uppercase;',
        }),
    )
    password = forms.CharField(
        required=False,
        widget=forms.PasswordInput(attrs={
            'class': 'form-input',
            'placeholder': 'Password (if required)',
        }),
    )
