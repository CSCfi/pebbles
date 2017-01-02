app.service('ConfigurationService', ['Restangular', function(Restangular) {
    var pbconfig = Restangular.all('config');
    this._config = null;

    this.getValue = function(key) {
        if (this._config == null) {
            this._config = pbconfig.getList().then(function(response) {
                var config = {};
                angular.forEach(response, function(v, k) {
                    config[v.key] = v.value;
                });
                return config;
            });
        }
        return this._config;
    };
}]);

