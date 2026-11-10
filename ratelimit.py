"""Limite les tentatives de connexion, pour freiner une attaque par force brute.

En mémoire du processus api : simple, sans dépendance, mais remis à zéro au
redémarrage et non partagé entre plusieurs processus. Suffisant pour ce TP.

La clé est l'email : l'API voit toutes les requêtes venir du pare-feu
(masquerade), donc l'adresse IP ne distingue pas les clients.
"""
import threading
import time


class LoginRateLimiter:
    def __init__(self, max_attempts=5, window=300):
        self.max_attempts = max_attempts
        self.window = window
        self._failures = {}
        self._lock = threading.Lock()

    def _recent(self, key, now):
        """Échecs encore dans la fenêtre ; nettoie les clés vides."""
        times = [t for t in self._failures.get(key, []) if now - t < self.window]
        if times:
            self._failures[key] = times
        else:
            self._failures.pop(key, None)
        return times

    def retry_after(self, key):
        """Secondes à attendre avant une nouvelle tentative, ou 0 si autorisé."""
        now = time.time()
        with self._lock:
            times = self._recent(key, now)
            if len(times) < self.max_attempts:
                return 0
            return int(self.window - (now - times[0])) + 1

    def record_failure(self, key):
        now = time.time()
        with self._lock:
            times = self._recent(key, now)
            times.append(now)
            self._failures[key] = times

    def reset(self, key):
        """Appelé après une connexion réussie : on efface le compteur."""
        with self._lock:
            self._failures.pop(key, None)

login_limiter = LoginRateLimiter(max_attempts=5, window=300)