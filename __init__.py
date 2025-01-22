# GPLv3 license
# Copyright Lutra Consulting Limited


def classFactory(iface):
    from .team_zones import TeamZonesPlugin

    return TeamZonesPlugin(iface)
