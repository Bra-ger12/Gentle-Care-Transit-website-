import factory
from factory.django import DjangoModelFactory

from apps.accounts.models import DriverProfile, RiderProfile, Role, User


class UserFactory(DjangoModelFactory):
    class Meta:
        model = User
        skip_postgeneration_save = True

    email = factory.Sequence(lambda n: f"user{n}@example.com")
    first_name = "Test"
    last_name = "User"
    role = Role.RIDER
    is_active = True
    # An established account, which is what most tests mean by "a user". Tests
    # about the verification flow itself set this to False explicitly.
    is_verified = True

    @factory.post_generation
    def password(self, create, extracted, **kwargs):
        self.set_password(extracted or "TestPass123!")
        if create:
            self.save()


class RiderFactory(UserFactory):
    role = Role.RIDER


class DriverFactory(UserFactory):
    role = Role.DRIVER


class AdminFactory(UserFactory):
    role = Role.ADMIN
    is_staff = True


class RiderProfileFactory(DjangoModelFactory):
    class Meta:
        model = RiderProfile

    user = factory.SubFactory(RiderFactory)
    city = "Fargo"
    state = "ND"


class DriverProfileFactory(DjangoModelFactory):
    class Meta:
        model = DriverProfile

    user = factory.SubFactory(DriverFactory)
    is_approved = True
