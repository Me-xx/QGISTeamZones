# GPLv3 license
# Copyright Lutra Consulting Limited


def classFactory(iface):
    from .TeamArea import TeamZonesPlugin

    return TeamZonesPlugin(iface)
