def institution_scoped(queryset, user, field="institution"):
    """
    Scopes `queryset` to `user`'s own institution — unless `user` is a
    superuser, who sees across every institution.

    `field` is the lookup path from the queryset's model to the
    Institution it belongs to:
      - "institution"                    — a direct FK (Program, User)
      - "program__institution"           — reached through a Program (Course)
      - "courses__program__institution"  — through a Course M2M (CourseAllocation)
        (call .distinct() on the result for any M2M-joined path)

    A non-superuser with no institution of their own (shouldn't normally
    happen — every org admin/facilitator/student gets one on creation)
    sees an empty queryset rather than everything, so a missing
    assignment fails closed instead of leaking cross-institution data.
    """
    if user.is_superuser:
        return queryset
    if not user.institution_id:
        return queryset.none()
    return queryset.filter(**{field: user.institution_id})
