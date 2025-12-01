# Maintainer: RitzDaCat <https://github.com/RitzDaCat>
pkgname=udev-autoconfig
pkgver=1.0.0
pkgrel=1
pkgdesc="Automatically generate udev rules for USB devices, enabling WebHID access for gaming peripherals"
arch=('any')
url="https://github.com/RitzDaCat/udev-autoconfig"
license=('MIT')
depends=('python' 'systemd')
optdepends=(
    'python-gobject: GUI support'
    'gtk4: GUI support'
    'libadwaita: GUI support'
    'polkit: GUI privilege escalation'
)
source=("$pkgname-$pkgver.tar.gz::$url/archive/v$pkgver.tar.gz")
sha256sums=('SKIP')

# For local development builds, use this instead:
# source=("git+$url.git")

package() {
    cd "$srcdir/$pkgname-$pkgver"
    
    # Install CLI tool
    install -Dm755 udev-autoconfig.py "$pkgdir/usr/bin/udev-autoconfig"
    
    # Install GUI tool
    install -Dm755 udev-autoconfig-gui.py "$pkgdir/usr/bin/udev-autoconfig-gui"
    
    # Install desktop entry
    install -Dm644 udev-autoconfig.desktop "$pkgdir/usr/share/applications/udev-autoconfig.desktop"
    
    # Install polkit policy for GUI privilege escalation
    install -Dm644 com.github.udev-autoconfig.policy "$pkgdir/usr/share/polkit-1/actions/com.github.udev-autoconfig.policy"
    
    # Install license
    install -Dm644 LICENSE "$pkgdir/usr/share/licenses/$pkgname/LICENSE"
    
    # Install documentation
    install -Dm644 README.md "$pkgdir/usr/share/doc/$pkgname/README.md"
}

