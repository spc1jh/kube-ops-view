import {ColorMatrixFilter} from 'pixi.js'

const BRIGHTNESS_FILTER = new ColorMatrixFilter()
BRIGHTNESS_FILTER.brightness(1.3, false)

const DESATURATION_FILTER = new ColorMatrixFilter()
DESATURATION_FILTER.desaturate()

export { BRIGHTNESS_FILTER, DESATURATION_FILTER }
