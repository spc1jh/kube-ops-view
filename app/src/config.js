const TRUTHY_VALUES = new Set(['1', 'true'])

// font sizes (px) offered by the tooltip size selector in the menu bar
export const TOOLTIP_FONT_SIZES = [12, 14, 16, 18, 20, 24, 28, 32, 40]

export default class Config {

    constructor() {
        this.dashboardMode = false
        this.reloadIntervalSeconds = 0
        this.initialScale = 1.0
        this.renderer = 'auto'
        // font size (px) of the tooltips, which are not affected by the view zoom
        this.tooltipFontSize = 16
        // make sure we got activity at least every 20 seconds
        this.keepAliveSeconds = 20
        // always reconnect after 5 minutes
        this.maxConnectionLifetimeSeconds = 300
        // consider cluster data older than 1 minute outdated
        this.maxDataAgeSeconds = 60

        this.nodeLinkUrlTemplate = null
        this.podLinkUrlTemplate = null
    }

    static fromParams(params) {
        const config = new Config()
        config.dashboardMode = TRUTHY_VALUES.has(params.get('dashboard'))
        config.reloadIntervalSeconds = parseInt(params.get('reload')) || 0
        config.initialScale = parseFloat(params.get('scale')) || 1.0
        config.renderer = params.get('renderer') || 'auto'
        config.tooltipFontSize = parseInt(params.get('tooltip')) || config.tooltipFontSize
        return config
    }


}
