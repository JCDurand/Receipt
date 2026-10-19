from django.contrib import admin

from .models import User, BankStatement, Tag, Transaction, Item, Receipt, Account

admin.site.register([User, BankStatement, Tag, Transaction, Item, Receipt, Account])
