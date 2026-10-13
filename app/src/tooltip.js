import {Container, Graphics, Text} from 'pixi.js'
import App from './app.js'

export default class Tooltip extends Container {
    constructor () {
        super()
        this.gfx = new Graphics()
        this.addChild(this.gfx)
        this.text = new Text({text: '', style: {fontFamily: 'ShareTechMono', fontSize: 12, fill: 0xffffff}})
        this.text.x = 4
        this.text.y = 4
        this.addChild(this.text)
        this.visible = false
    }

    setText(text) {
        this.text.text = text
        this.draw()
    }

    draw () {
        this.gfx.clear()
        this.gfx.rect(0, 0, this.text.width + 8, this.text.height + 8)
        this.gfx.fill({color: App.current.theme.secondaryColor, alpha: 0.8})
        this.gfx.stroke({width: 2, color: App.current.theme.secondaryColor, alpha: 0.8})
    }
}
