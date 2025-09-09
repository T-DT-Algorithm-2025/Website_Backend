def is_admin_check(permission_info):
    return permission_info and (
        permission_info.get('is_main_leader_admin') or 
        permission_info.get('is_group_leader_admin') or 
        permission_info.get('is_member_admin')
    )
