from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views
from .views import BudgetViewSet, TagViewSet, transaction_tags

router = DefaultRouter()

router.register(r"tags", TagViewSet, basename="tag")
router.register(r"budgets", BudgetViewSet, basename="budget")

urlpatterns = [
    path("health/", views.health_check, name="health-check"),
    path("", views.transaction_list),
    path("transaction/<uuid:pk>/", transaction_tags),
    path("accounts/", views.account_list, name="account-list"),
    path("accounts/history/", views.AccountHistoryView.as_view(), name="account-history"),
    path("accounts/<uuid:pk>/", views.AccountDetailView.as_view(), name="account-detail"),
    path("upload/", views.upload_statement),
    path("register/", views.register_user),
    path("documents/", views.DocumentListView.as_view(), name="document-list"),
    path(
        "documents/upload/",
        views.UnifiedDocumentUploadView.as_view(),
        name="document-upload",
    ),
    path(
        "documents/manual/",
        views.ManualEntryUploadView.as_view(),
        name="document-manual-entry",
    ),
    path(
        "documents/parse/",
        views.DocumentParseView.as_view(),
        name="document-parse",
    ),
    path(
        "documents/statements/<uuid:pk>/",
        views.StatementDetailView.as_view(),
        name="statement-detail",
    ),
    path(
        "documents/items/<uuid:item_id>/link/",
        views.ItemLinkView.as_view(),
        name="item-link",
    ),
    path(
        "documents/items/<uuid:pk>/tags/",
        views.ItemTagsView.as_view(),
        name="item-tags",
    ),
    path(
        "documents/transactions/<uuid:pk>/tags/",
        views.TransactionTagsView.as_view(),
        name="transaction-tags",
    ),
    path(
        "documents/items/<uuid:pk>/subscription/",
        views.ItemSubscriptionView.as_view(),
        name="item-subscription",
    ),
    path(
        "documents/transactions/<uuid:pk>/subscription/",
        views.TransactionSubscriptionView.as_view(),
        name="transaction-subscription",
    ),
    path("subscriptions/", views.SubscriptionListView.as_view(), name="subscription-list"),
    path(
        "documents/items/<uuid:pk>/",
        views.ItemRemoveView.as_view(),
        name="item-remove",
    ),
    path(
        "documents/transactions/<uuid:pk>/",
        views.TransactionRemoveView.as_view(),
        name="transaction-remove",
    ),
    path(
        "documents/items/<uuid:pk>/details/",
        views.ItemDetailsView.as_view(),
        name="item-details",
    ),
    path(
        "documents/transactions/<uuid:pk>/details/",
        views.TransactionDetailsView.as_view(),
        name="transaction-details",
    ),
    path(
        "documents/receipts/<uuid:pk>/account/",
        views.ReceiptAccountView.as_view(),
        name="receipt-account",
    ),
    path("settings/", views.SettingsView.as_view(), name="settings"),
    path("line-items/", views.LineItemListView.as_view(), name="line-item-list"),
    path("line-items/delete/", views.LineItemBulkDeleteView.as_view(), name="line-item-bulk-delete"),
    path(
        "documents/<str:pk>/",
        views.UnifiedDocumentDeleteView.as_view(),
        name="document-delete",
    ),
    path(
        "documents/<str:pk>/file/",
        views.UnifiedDocumentFileView.as_view(),
        name="document-file",
    ),
    path(
        "documents/<str:pk>/rename/",
        views.UnifiedDocumentRenameView.as_view(),
        name="document-rename",
    ),
    path(
        "documents/update/<str:receiptId>/",
        views.UnifiedDocumentUpdateView.as_view(),
        name="document-update",
    ),
    path("item/<uuid:pk>/", views.item_detail, name="item_detail"),
    path('templates/', views.TransactionTemplateListCreateView.as_view(), name='template-list-create'),
    path('templates/<str:pk>/', views.TransactionTemplateDestroyView.as_view(), name='template-delete'),
    path("", include(router.urls)),
]
