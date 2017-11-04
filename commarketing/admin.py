from django.contrib import admin


class BannerAdmin(admin.ModelAdmin):
    fields = ('title', 'display', 'cta', 'content_type', )


class SmartCategoryAdmin(admin.ModelAdmin):
    fields = ('title', 'content_type', 'badge_text',)
